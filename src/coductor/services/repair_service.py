"""Failure repair request/result artifact handling."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    FileReference,
    GateReportData,
    GoalSatisfactionReportData,
    Producer,
    RepairRequestData,
    TaskData,
    ToolResultData,
    WorkerResultData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import CodingBackend, WorkerHandle, WorkerRequest
from coductor.backends.capabilities import describe_backend_capability, effective_backend_provider
from coductor.backends.factory import is_codex_sdk_available
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ProducerKind, SandboxMode
from coductor.prompts.renderer import PromptSection, render_worker_prompt
from coductor.services.task_execution_service import TaskExecutionService
from coductor.services.usage import usage_from_backend
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class RepairService:
    def __init__(
        self,
        root: Path,
        config: CoductorConfig,
        backend: CodingBackend,
        artifacts: WorkflowArtifactWriter,
    ) -> None:
        self.root = root
        self.config = config
        self.backend = backend
        self.artifacts = artifacts

    def repair(
        self,
        repo: ArtifactRepository,
        run_id: str,
        builder_handle: WorkerHandle,
        gate_report: ArtifactEnvelope[GateReportData],
        attempt: int,
        target_task_id: str,
        *,
        reason: Literal["gate_failure", "goal_not_satisfied", "missing_evidence"] = "gate_failure",
        goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData] | None = None,
    ) -> None:
        failed = [gate.id for gate in gate_report.data.gates if gate.status != "passed"]
        fingerprints = [
            gate.failure_fingerprint for gate in gate_report.data.gates if gate.failure_fingerprint
        ]
        missing_criteria = _missing_criteria(goal_satisfaction)
        missing_evidence = _missing_evidence(goal_satisfaction)
        evidence_paths = ["05_gate_report.yaml"]
        if goal_satisfaction is not None:
            evidence_paths.append("07_goal_satisfaction.yaml")
            evidence_paths.extend(_goal_evidence_paths(repo, goal_satisfaction))
            fingerprints.extend(_goal_failure_fingerprints(goal_satisfaction))
        repair_id = f"R{attempt:03d}"
        repair_dir = f"repairs/{repair_id}"
        sdk_available = is_codex_sdk_available()
        effective_provider = effective_backend_provider(
            self.config.backend.provider,
            fallback=self.config.backend.fallback,
            sdk_available=sdk_available,
        )
        can_resume_thread = describe_backend_capability(
            effective_provider,
            sdk_available=sdk_available,
        ).supports_resume_thread
        resume_thread_id = builder_handle.thread_id if can_resume_thread else None
        allowed_paths, forbidden_paths = self._target_task_path_boundaries(
            repo,
            target_task_id,
        )
        request_data = RepairRequestData(
            repair_id=repair_id,
            target_task_id=target_task_id,
            resume_thread_id=resume_thread_id,
            attempt=attempt,
            max_attempts=self.config.workflow.max_repair_attempts,
            reason=reason,
            failed_gates=failed,
            failure_fingerprints=[fp for fp in fingerprints if fp],
            evidence_paths=evidence_paths,
            missing_criteria=missing_criteria,
            missing_evidence=missing_evidence,
            recommended_action=_recommended_action(reason, goal_satisfaction),
            allowed_paths=allowed_paths,
            forbidden_paths=forbidden_paths,
            instruction=_repair_instruction(reason, goal_satisfaction),
        )
        request_envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPAIR_REQUEST,
            artifact_id_prefix="art_repair_req",
            status=ArtifactStatus.READY,
            producer=Producer(kind=ProducerKind.SYSTEM, name="repair-planner"),
            data=request_data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for("05_gate_report.yaml", gate_report)
                ),
                *(
                    [
                        ArtifactInput.model_validate(
                            repo.input_for("07_goal_satisfaction.yaml", goal_satisfaction)
                        )
                    ]
                    if goal_satisfaction is not None
                    else []
                ),
            ],
        )
        repo.write(f"{repair_dir}/repair_request.yaml", request_envelope)
        request = WorkerRequest(
            worker_id=f"worker_{target_task_id}_repair",
            role="repairer",
            prompt=render_worker_prompt(
                "repairer",
                _repair_context_artifacts(repo, evidence_paths),
                request_data.instruction,
                sections=_repair_prompt_sections(request_data, gate_report, goal_satisfaction),
            ),
            workspace_path=self.root.as_posix(),
            sandbox=SandboxMode.WORKSPACE_WRITE,
            thread_policy="resume" if can_resume_thread else "new",
            existing_thread_id=resume_thread_id,
        )
        diff_helper = TaskExecutionService(self.root, self.config, self.backend, self.artifacts)
        before_snapshot = diff_helper.workspace_snapshot(self.root)
        started_at = time.monotonic()
        result = self.backend.continue_worker(builder_handle, request)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        patch = repo.root / f"{repair_dir}/repair_result.patch"
        diff = diff_helper.workspace_diff(self.root)
        if not diff.strip():
            diff = diff_helper.snapshot_diff(
                before_snapshot,
                diff_helper.workspace_snapshot(self.root),
            )
        if diff.strip():
            patch.write_text(diff, encoding="utf-8")
        else:
            patch.write_text("# coductor no repair diff captured\n", encoding="utf-8")
        usage = usage_from_backend(
            result.usage,
            prompt=request.prompt,
            summary=result.summary,
            duration_ms=duration_ms,
        )
        result_data = WorkerResultData(
            worker_id=result.worker_id,
            thread_id=result.thread_id,
            task_id=target_task_id,
            summary=result.summary,
            patch=FileReference(
                path=f"{repair_dir}/repair_result.patch",
                sha256=file_sha256(patch),
                bytes=patch.stat().st_size,
            ),
            usage=usage,
            exit_reason=result.exit_reason,
        )
        result_envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPAIR_RESULT,
            artifact_id_prefix="art_repair_result",
            status=ArtifactStatus.COMPLETED,
            producer=Producer(kind=ProducerKind.MODEL, name="repair-worker"),
            data=result_data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for(f"{repair_dir}/repair_request.yaml", request_envelope)
                )
            ],
        )
        repo.write(f"{repair_dir}/repair_result.yaml", result_envelope)

    def _target_task_path_boundaries(
        self,
        repo: ArtifactRepository,
        target_task_id: str,
    ) -> tuple[list[str], list[str]]:
        task_path = f"tasks/{target_task_id}/task.yaml"
        if not (repo.root / task_path).exists():
            return ["src/**", "tests/**"], []
        task = ArtifactEnvelope[TaskData].model_validate(
            repo.read(task_path, ArtifactType.TASK).model_dump(mode="json")
        )
        return task.data.allowed_paths, task.data.forbidden_paths


def _missing_criteria(
    goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData] | None,
) -> list[str]:
    if goal_satisfaction is None:
        return []
    return [
        result.criterion_id
        for result in goal_satisfaction.data.criterion_results
        if result.status != "satisfied"
    ]


def _missing_evidence(
    goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData] | None,
) -> list[str]:
    if goal_satisfaction is None:
        return []
    return sorted(
        {
            evidence
            for result in goal_satisfaction.data.criterion_results
            for evidence in result.missing_evidence
        }
    )


def _goal_failure_fingerprints(
    goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData],
) -> list[str]:
    return [
        ":".join(
            [
                "goal",
                result.criterion_id,
                result.status,
                ",".join(sorted(result.missing_evidence)),
            ]
        )
        for result in goal_satisfaction.data.criterion_results
        if result.status != "satisfied"
    ]


def _recommended_action(
    reason: str,
    goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData] | None,
) -> str | None:
    if reason == "gate_failure":
        return "修复失败质量门"
    if goal_satisfaction is None:
        return "补齐目标满足证据"
    return goal_satisfaction.data.repair_recommendation or "补齐目标满足证据"


def _repair_instruction(
    reason: str,
    goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData] | None,
) -> str:
    if reason == "gate_failure":
        return "只修复导致当前 Gate 失败的最小范围，不进行无关重构。"
    missing_criteria = ", ".join(_missing_criteria(goal_satisfaction)) or "unknown"
    missing_evidence = ", ".join(_missing_evidence(goal_satisfaction)) or "none"
    return (
        "只修复导致目标满足度未通过的最小范围。"
        f"未满足验收标准: {missing_criteria}。"
        f"缺失证据: {missing_evidence}。"
        "必要时补实现、补自动化验证或补证据文件，然后保持质量门可通过。"
    )


def _repair_context_artifacts(
    repo: ArtifactRepository,
    evidence_paths: list[str],
) -> list[str]:
    paths = ["02_spec.yaml", "03_verification_plan.yaml", *evidence_paths]
    deduped: list[str] = []
    for path in paths:
        if path in deduped:
            continue
        if path in evidence_paths or (repo.root / path).exists():
            deduped.append(path)
    return deduped


def _repair_prompt_sections(
    request: RepairRequestData,
    gate_report: ArtifactEnvelope[GateReportData],
    goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData] | None,
) -> list[PromptSection]:
    failed_gates = [
        (
            f"{gate.id}: status={gate.status}, command={gate.command}, "
            f"stdout={gate.stdout_path}, stderr={gate.stderr_path}, "
            f"fingerprint={gate.failure_fingerprint or '(none)'}"
        )
        for gate in gate_report.data.gates
        if gate.status != "passed"
    ]
    goal_items = []
    if goal_satisfaction is not None:
        goal_items = [
            (
                f"{result.criterion_id}: status={result.status}, "
                f"evidence={', '.join(result.evidence) or '(none)'}, "
                f"missing_evidence={', '.join(result.missing_evidence) or '(none)'}, "
                f"reason={result.reason}"
            )
            for result in goal_satisfaction.data.criterion_results
            if result.status != "satisfied"
        ]
    return [
        PromptSection(
            "Repair Request",
            [
                f"reason: {request.reason}",
                f"attempt: {request.attempt}/{request.max_attempts}",
                f"target_task_id: {request.target_task_id}",
                f"recommended_action: {request.recommended_action or '(none)'}",
            ],
        ),
        PromptSection("Failed Gates", failed_gates or ["No failed quality gates."]),
        PromptSection(
            "Goal Satisfaction Gaps",
            goal_items or ["No goal satisfaction gaps provided."],
        ),
        PromptSection(
            "Missing Evidence",
            request.missing_evidence or ["No missing evidence paths listed."],
        ),
        PromptSection(
            "Path Boundaries",
            [
                f"allowed_paths: {', '.join(request.allowed_paths) or '(none)'}",
                f"forbidden_paths: {', '.join(request.forbidden_paths) or '(none)'}",
            ],
        ),
    ]


def _goal_evidence_paths(
    repo: ArtifactRepository,
    goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData],
) -> list[str]:
    paths: list[str] = []
    for result in goal_satisfaction.data.criterion_results:
        if result.status == "satisfied":
            continue
        for evidence_path in result.evidence:
            if evidence_path in paths:
                continue
            paths.append(evidence_path)
            if _is_tool_result_path(evidence_path) and (repo.root / evidence_path).exists():
                paths.extend(_tool_artifact_paths(repo, evidence_path))
    return list(dict.fromkeys(paths))


def _tool_artifact_paths(repo: ArtifactRepository, evidence_path: str) -> list[str]:
    try:
        envelope = repo.read(evidence_path, ArtifactType.TOOL_RESULT)
        result = ToolResultData.model_validate(envelope.data)
    except (OSError, ValueError):
        return []
    return [path for path in result.artifacts if (repo.root / path).exists()]


def _is_tool_result_path(path: str) -> bool:
    return path.startswith("tool_runs/") and path.endswith("/tool_result.yaml")
