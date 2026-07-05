"""Stage artifact writers for the deterministic workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    ArtifactMetadata,
    GateReportData,
    GoalCriterionResult,
    GoalData,
    GoalSatisfactionReportData,
    Producer,
    RepositorySnapshotData,
    SpecificationData,
    ToolResultData,
    VerificationPlanData,
    VerificationPlanItem,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig, ImageGenerationConfig, ToolCheckConfig
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ExecutionStrategy,
    ProducerKind,
    VerificationType,
)
from coductor.domain.ids import new_id
from coductor.domain.tool_paths import tool_result_path_for_check
from coductor.planning.planner import (
    choose_strategy,
    create_parallel_plan,
    create_pipeline_plan,
    create_solo_plan,
)
from coductor.planning.spec_builder import build_acceptance_criteria, derive_in_scope
from coductor.repository.inspector import RepositoryInspector


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class WorkflowArtifactWriter:
    def __init__(self, root: Path, config: CoductorConfig) -> None:
        self.root = root
        self.config = config

    def envelope(
        self,
        *,
        run_id: str,
        artifact_type: ArtifactType,
        artifact_id_prefix: str,
        status: ArtifactStatus | str,
        producer: Producer,
        data: Any,
        inputs: list[ArtifactInput] | None = None,
    ) -> ArtifactEnvelope[Any]:
        return ArtifactEnvelope[Any](
            artifact_type=artifact_type,
            artifact_id=new_id(artifact_id_prefix),
            run_id=run_id,
            revision=1,
            status=status,
            created_at=utc_now(),
            producer=producer,
            inputs=inputs or [],
            metadata=ArtifactMetadata(),
            data=data,
        )

    def write_goal(
        self,
        repo: ArtifactRepository,
        run_id: str,
        raw_goal: str,
        requested_mode: ExecutionMode,
    ) -> ArtifactEnvelope[GoalData]:
        goal_type = (
            "bugfix"
            if any(word in raw_goal for word in ["修复", "fix", "bug"])
            else "feature"
        )
        data = GoalData(
            title=raw_goal[:60],
            raw_request=raw_goal,
            goal_type=goal_type,
            requested_mode=requested_mode,
            target_repository=".",
            user_constraints=[],
        )
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.GOAL,
            artifact_id_prefix="art_goal",
            status=ArtifactStatus.ACCEPTED,
            producer=Producer(kind=ProducerKind.HUMAN, name="cli-user"),
            data=data,
        )
        repo.write("00_goal.yaml", envelope)
        return envelope

    def write_snapshot(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
    ) -> ArtifactEnvelope[RepositorySnapshotData]:
        data = RepositoryInspector(self.root, self.config).inspect()
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPOSITORY_SNAPSHOT,
            artifact_id_prefix="art_repo",
            status=ArtifactStatus.COMPLETE,
            producer=Producer(kind=ProducerKind.SYSTEM, name="repository-inspector"),
            inputs=[ArtifactInput.model_validate(repo.input_for("00_goal.yaml", goal))],
            data=data,
        )
        repo.write("01_repository_snapshot.yaml", envelope)
        return envelope

    def write_spec(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
        snapshot: ArtifactEnvelope[RepositorySnapshotData],
    ) -> ArtifactEnvelope[SpecificationData]:
        data = SpecificationData(
            objective=goal.data.raw_request,
            in_scope=derive_in_scope(goal.data.raw_request),
            out_of_scope=["Web 控制台", "自动 PR", "远程推送", "生产环境操作"],
            constraints=[
                "危险能力默认关闭",
                "完成状态只由质量门和审查证据决定",
            ],
            assumptions=[],
            acceptance_criteria=build_acceptance_criteria(goal.data.raw_request),
            risks=snapshot.data.risks,
            unresolved_questions=[],
        )
        if self.config.workflow.require_spec_approval:
            data.approval.required = True
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.SPECIFICATION,
            artifact_id_prefix="art_spec",
            status=ArtifactStatus.APPROVED,
            producer=Producer(kind=ProducerKind.MODEL, name="specification-agent"),
            inputs=[
                ArtifactInput.model_validate(repo.input_for("00_goal.yaml", goal)),
                ArtifactInput.model_validate(
                    repo.input_for("01_repository_snapshot.yaml", snapshot)
                ),
            ],
            data=data,
        )
        repo.write("02_spec.yaml", envelope)
        return envelope

    def write_plan(
        self,
        repo: ArtifactRepository,
        run_id: str,
        spec: ArtifactEnvelope[SpecificationData],
        snapshot: ArtifactEnvelope[RepositorySnapshotData],
        requested_mode: ExecutionMode,
    ) -> ArtifactEnvelope[Any]:
        decision = choose_strategy(spec.data.objective, requested_mode=requested_mode)
        if decision.strategy == ExecutionStrategy.PIPELINE:
            data = create_pipeline_plan(
                spec.data,
                snapshot.data.base_commit,
                decision.reasoning,
                quality_gate_ids=[gate.id for gate in self.config.quality_gates],
            )
        elif decision.strategy == ExecutionStrategy.PARALLEL:
            data = create_parallel_plan(
                spec.data,
                snapshot.data.base_commit,
                decision.reasoning,
                snapshot.data,
                quality_gate_ids=[gate.id for gate in self.config.quality_gates],
            )
        else:
            data = create_solo_plan(
                spec.data,
                snapshot.data.base_commit,
                snapshot.data,
                quality_gate_ids=[gate.id for gate in self.config.quality_gates],
            )
        if (
            data.strategy == ExecutionStrategy.PARALLEL
            and self.config.workflow.require_plan_approval_for_parallel
        ):
            data.approval.required = True
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.EXECUTION_PLAN,
            artifact_id_prefix="art_plan",
            status=ArtifactStatus.VALIDATED if data.validation.valid else ArtifactStatus.FAILED,
            producer=Producer(kind=ProducerKind.MODEL, name="planning-agent"),
            inputs=[
                ArtifactInput.model_validate(repo.input_for("02_spec.yaml", spec)),
                ArtifactInput.model_validate(
                    repo.input_for("01_repository_snapshot.yaml", snapshot)
                ),
            ],
            data=data,
        )
        repo.write("03_execution_plan.yaml", envelope)
        return envelope

    def write_verification_plan(
        self,
        repo: ArtifactRepository,
        run_id: str,
        spec: ArtifactEnvelope[SpecificationData],
    ) -> ArtifactEnvelope[VerificationPlanData]:
        items = [
            VerificationPlanItem(
                id=f"VP{index:03d}",
                criterion_id=criterion.id,
                description=criterion.statement,
                verification=criterion.verification,
                tool=_verification_tool_name(
                    criterion.statement,
                    criterion.verification,
                    _tool_checks_for_criterion(self.config, criterion.id),
                ),
                required=criterion.priority == "required",
                commands=_verification_commands(self.config, criterion),
                evidence_paths=_verification_evidence_paths(
                    self.config,
                    criterion.id,
                    criterion.statement,
                    criterion.verification,
                ),
                fallback_if_unavailable=(
                    "进入 human_required，由人工确认该验收标准"
                    if criterion.verification != VerificationType.AUTOMATED
                    else None
                ),
            )
            for index, criterion in enumerate(spec.data.acceptance_criteria, start=1)
        ]
        required_unplanned = [
            item.criterion_id
            for item in items
            if item.required and not item.evidence_paths and item.tool != "manual"
        ]
        data = VerificationPlanData(
            items=items,
            all_required_criteria_planned=not required_unplanned,
            warnings=[
                f"required criterion {criterion_id} has no automated evidence path"
                for criterion_id in required_unplanned
            ],
        )
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.VERIFICATION_PLAN,
            artifact_id_prefix="art_verification_plan",
            status=ArtifactStatus.READY,
            producer=Producer(kind=ProducerKind.SYSTEM, name="verification-planner"),
            inputs=[ArtifactInput.model_validate(repo.input_for("02_spec.yaml", spec))],
            data=data,
        )
        if (repo.root / "03_verification_plan.yaml").exists():
            repo.write_next_revision("03_verification_plan.yaml", envelope)
        else:
            repo.write("03_verification_plan.yaml", envelope)
        return envelope

    def write_goal_satisfaction(
        self,
        repo: ArtifactRepository,
        run_id: str,
        verification_plan: ArtifactEnvelope[VerificationPlanData],
        gate_report: ArtifactEnvelope[GateReportData],
    ) -> ArtifactEnvelope[GoalSatisfactionReportData]:
        results: list[GoalCriterionResult] = []
        missing_evidence: list[str] = []
        for item in verification_plan.data.items:
            existing_evidence = [
                path for path in item.evidence_paths if (repo.root / path).exists()
            ]
            item_missing = [
                path for path in item.evidence_paths if not (repo.root / path).exists()
            ]
            tool_failures = _tool_result_failures(repo, item.evidence_paths)
            tool_human_requirements = _tool_result_human_requirements(
                repo,
                item.evidence_paths,
            )
            if item.tool == "quality_gate":
                if (
                    gate_report.data.required_gates_passed
                    and not item_missing
                    and not tool_failures
                ):
                    status: Literal["satisfied", "not_satisfied", "uncertain"] = "satisfied"
                    reason = "required quality gates passed"
                elif item_missing:
                    status = "not_satisfied"
                    reason = "planned evidence is missing"
                elif tool_human_requirements:
                    status = "uncertain"
                    reason = (
                        "planned tool evidence requires human: "
                        f"{'; '.join(tool_human_requirements)}"
                    )
                elif tool_failures:
                    status = "not_satisfied"
                    reason = f"planned tool evidence failed: {'; '.join(tool_failures)}"
                else:
                    status = "not_satisfied"
                    reason = "required quality gates failed"
            elif item.tool == "quality_gate+tool_check":
                if item_missing:
                    status = "not_satisfied"
                    reason = "planned evidence is missing"
                elif not gate_report.data.required_gates_passed:
                    status = "not_satisfied"
                    reason = "required quality gates failed"
                elif tool_human_requirements:
                    status = "uncertain"
                    reason = (
                        "planned tool evidence requires human: "
                        f"{'; '.join(tool_human_requirements)}"
                    )
                elif tool_failures:
                    status = "not_satisfied"
                    reason = f"planned tool evidence failed: {'; '.join(tool_failures)}"
                else:
                    status = "satisfied"
                    reason = "required quality gates and tool checks passed"
            elif item.tool == "manual":
                status = "uncertain"
                reason = "manual verification is required"
            elif item_missing:
                status = "not_satisfied"
                reason = "planned tool evidence is missing"
            elif tool_human_requirements:
                status = "uncertain"
                reason = (
                    "planned tool evidence requires human: "
                    f"{'; '.join(tool_human_requirements)}"
                )
            elif tool_failures:
                status = "not_satisfied"
                reason = f"planned tool evidence failed: {'; '.join(tool_failures)}"
            else:
                status = "satisfied"
                reason = "planned tool evidence exists"
            missing_evidence.extend(item_missing)
            results.append(
                GoalCriterionResult(
                    criterion_id=item.criterion_id,
                    status=status,
                    evidence=existing_evidence,
                    missing_evidence=item_missing,
                    reason=reason,
                )
            )
        required_results = [
            result
            for item, result in zip(verification_plan.data.items, results, strict=True)
            if item.required
        ]
        verdict: Literal["satisfied", "not_satisfied", "uncertain"]
        if any(result.status == "not_satisfied" for result in required_results):
            verdict = "not_satisfied"
        elif any(result.status == "uncertain" for result in required_results):
            verdict = "uncertain"
        else:
            verdict = "satisfied"
        data = GoalSatisfactionReportData(
            verdict=verdict,
            criterion_results=results,
            missing_evidence=sorted(set(missing_evidence)),
            repair_recommendation=(
                "补齐缺失证据或修复未满足的验收标准"
                if verdict != "satisfied"
                else None
            ),
            requires_repair=verdict == "not_satisfied",
            requires_human=verdict == "uncertain",
        )
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.GOAL_SATISFACTION_REPORT,
            artifact_id_prefix="art_goal_satisfaction",
            status=(
                ArtifactStatus.PASSED
                if verdict == "satisfied"
                else ArtifactStatus.HUMAN_REQUIRED
            ),
            producer=Producer(kind=ProducerKind.SYSTEM, name="goal-satisfaction-evaluator"),
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for("03_verification_plan.yaml", verification_plan)
                ),
                ArtifactInput.model_validate(repo.input_for("05_gate_report.yaml", gate_report)),
                *_tool_result_inputs(repo, verification_plan),
            ],
            data=data,
        )
        if (repo.root / "07_goal_satisfaction.yaml").exists():
            repo.write_next_revision("07_goal_satisfaction.yaml", envelope)
        else:
            repo.write("07_goal_satisfaction.yaml", envelope)
        return envelope


def _tool_checks_for_criterion(
    config: CoductorConfig,
    criterion_id: str,
) -> list[ToolCheckConfig]:
    return [
        check
        for check in config.tool_checks
        if not check.criterion_ids or criterion_id in check.criterion_ids
    ]


def _verification_tool_name(
    statement: str,
    verification: VerificationType,
    tool_checks: list[Any],
) -> str:
    if verification != VerificationType.AUTOMATED:
        return "manual"
    if _statement_needs_image_asset(statement):
        return "image_generation"
    return "quality_gate+tool_check" if tool_checks else "quality_gate"


def _verification_evidence_paths(
    config: CoductorConfig,
    criterion_id: str,
    statement: str,
    verification: VerificationType,
) -> list[str]:
    if verification != VerificationType.AUTOMATED:
        return []
    if _statement_needs_image_asset(statement):
        return [tool_result_path_for_check(_image_check_id(criterion_id))]
    paths = ["05_gate_report.yaml"]
    for check in _tool_checks_for_criterion(config, criterion_id):
        paths.append(tool_result_path_for_check(check.id))
        paths.extend(check.evidence_paths)
    return sorted(dict.fromkeys(paths))


def _verification_commands(
    config: CoductorConfig,
    criterion: Any,
) -> list[str]:
    if (
        criterion.verification == VerificationType.AUTOMATED
        and _statement_needs_image_asset(criterion.statement)
    ):
        return ["image-asset-request"]
    return [
        *[gate.command for gate in config.quality_gates],
        *[
            check.command
            for check in _tool_checks_for_criterion(
                config,
                criterion.id,
            )
        ],
    ]


def _tool_result_failures(repo: ArtifactRepository, evidence_paths: list[str]) -> list[str]:
    failures: list[str] = []
    for path in evidence_paths:
        if not _is_tool_result_path(path) or not (repo.root / path).exists():
            continue
        try:
            envelope = repo.read(path, ArtifactType.TOOL_RESULT)
            result = ToolResultData.model_validate(envelope.data)
        except (OSError, ValueError) as exc:
            failures.append(f"{path}: invalid ({exc})")
            continue
        if result.required and result.status != "passed":
            failures.append(f"{path}: {result.status}")
    return failures


def _tool_result_human_requirements(
    repo: ArtifactRepository,
    evidence_paths: list[str],
) -> list[str]:
    requirements: list[str] = []
    for path in evidence_paths:
        if not _is_tool_result_path(path) or not (repo.root / path).exists():
            continue
        try:
            envelope = repo.read(path, ArtifactType.TOOL_RESULT)
            result = ToolResultData.model_validate(envelope.data)
        except (OSError, ValueError):
            continue
        if result.required and result.observations.get("requires_human") is True:
            action = result.observations.get("human_action", "human_required")
            requirements.append(f"{path}: {action}")
    return requirements


def _tool_result_inputs(
    repo: ArtifactRepository,
    verification_plan: ArtifactEnvelope[VerificationPlanData],
) -> list[ArtifactInput]:
    inputs: list[ArtifactInput] = []
    seen: set[str] = set()
    for item in verification_plan.data.items:
        for path in item.evidence_paths:
            if path in seen or not _is_tool_result_path(path) or not (repo.root / path).exists():
                continue
            seen.add(path)
            tool_result = repo.read(path, ArtifactType.TOOL_RESULT)
            inputs.append(ArtifactInput.model_validate(repo.input_for(path, tool_result)))
    return inputs


def _is_tool_result_path(path: str) -> bool:
    return path.startswith("tool_runs/") and path.endswith("/tool_result.yaml")


def _statement_needs_image_asset(statement: str) -> bool:
    normalized = statement.lower()
    return any(
        marker in normalized
        for marker in ["图片资产", "图片", "图像", "生图", "image", "asset"]
    )


def _image_check_id(criterion_id: str) -> str:
    return f"image_asset_{criterion_id.lower()}"


def implicit_image_check_for_item(item: VerificationPlanItem) -> ToolCheckConfig | None:
    if item.tool != "image_generation":
        return None
    return ToolCheckConfig(
        id=_image_check_id(item.criterion_id),
        tool="image_generation",
        required=item.required,
        description=item.description,
        criterion_ids=[item.criterion_id],
        image=ImageGenerationConfig(
            prompt=item.description,
            purpose=f"满足验收标准 {item.criterion_id}",
            output_path=f"assets/generated/{item.criterion_id.lower()}.png",
            candidate_count=1,
        ),
    )
