"""Evidence bundle and report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    AcceptanceCoverage,
    EvidenceBundleData,
    EvidenceFile,
    EvidenceValidation,
    GateReportData,
    GateSummary,
    GoalSatisfactionReportData,
    GoalSatisfactionSummary,
    PullRequestInfo,
    ReviewReportData,
    ReviewSummary,
    Rollback,
    WorkerUsage,
)
from coductor.artifacts.serializer import load_yaml
from coductor.domain.enums import ExecutionStrategy
from coductor.services.usage import combine_usage


class EvidenceCompletenessValidator:
    def validate(self, evidence: EvidenceBundleData) -> EvidenceValidation:
        errors: list[str] = []
        if evidence.gate_summary.failed > 0:
            errors.append("required gates failed")
        if evidence.review_summary.blocking_findings > 0:
            errors.append("blocking review findings exist")
        if evidence.goal_satisfaction.verdict != "satisfied":
            errors.append("goal satisfaction is not satisfied")
        if not any(item.type == "patch" for item in evidence.evidence_files):
            errors.append("missing patch evidence")
        if any(item.type == "invalid_patch" for item in evidence.evidence_files):
            errors.append("patch evidence has no changes")
        return EvidenceValidation(valid=not errors, errors=errors)


class EvidenceService:
    def build(
        self,
        *,
        run_dir: Path,
        goal_title: str,
        strategy: ExecutionStrategy,
        gate_report: GateReportData,
        review: ReviewReportData,
        completed_tasks: list[str],
        goal_satisfaction: GoalSatisfactionReportData | None = None,
    ) -> EvidenceBundleData:
        required = [gate for gate in gate_report.gates if gate.required]
        passed = [gate for gate in required if gate.status == "passed"]
        failed = [gate for gate in required if gate.status != "passed"]
        usage_summary = combine_usage([*_artifact_usages(run_dir), review.usage])
        evidence_files: list[EvidenceFile] = []
        for task_id in completed_tasks:
            patch_path = run_dir / f"tasks/{task_id}/patch.diff"
            if not patch_path.exists():
                continue
            patch_type = "patch" if _patch_has_changes(patch_path) else "invalid_patch"
            evidence_files.append(
                EvidenceFile(
                    type=patch_type,
                    path=f"tasks/{task_id}/patch.diff",
                    sha256=file_sha256(patch_path),
                )
            )
        for tool_result_path in sorted((run_dir / "tool_runs").glob("*/tool_result.yaml")):
            evidence_files.append(
                EvidenceFile(
                    type="tool_result",
                    path=tool_result_path.relative_to(run_dir).as_posix(),
                    sha256=file_sha256(tool_result_path),
                )
            )
            for artifact_path in _tool_result_artifacts(run_dir, tool_result_path):
                evidence_files.append(
                    EvidenceFile(
                        type=_tool_artifact_type(artifact_path),
                        path=artifact_path.relative_to(run_dir).as_posix(),
                        sha256=file_sha256(artifact_path),
                    )
                )
        evidence = EvidenceBundleData(
            goal_title=goal_title,
            final_status="ready_for_human_review",
            strategy_used=strategy,
            base_commit=gate_report.base_commit,
            head_commit=gate_report.head_commit,
            completed_tasks=completed_tasks,
            acceptance_results=_acceptance_results(
                gate_report,
                goal_satisfaction,
                failed=bool(failed),
            ),
            gate_summary=GateSummary(
                required=len(required),
                passed=len(passed),
                failed=len(failed),
            ),
            review_summary=ReviewSummary(blocking_findings=review.blocking_findings),
            goal_satisfaction=_goal_satisfaction_summary(goal_satisfaction),
            usage_summary=usage_summary,
            evidence_files=evidence_files,
            known_risks=[] if not failed else ["存在未通过的必需质量门"],
            manual_checks=[],
            rollback=Rollback(
                method="git reset/revert",
                instructions="在人工确认后使用 Git revert 或 reset 回滚变更。",
            ),
            pull_request=PullRequestInfo(
                created=False,
                title=goal_title,
                body_path="delivery-report.md",
            ),
        )
        validation = EvidenceCompletenessValidator().validate(evidence)
        evidence.validation = validation
        if not validation.valid:
            evidence.final_status = "human_required"
        return evidence

    def write_report(self, run_dir: Path, evidence: EvidenceBundleData) -> Path:
        report = run_dir / "delivery-report.md"
        lines = [
            "# Coductor Delivery Report",
            "",
            f"- Goal: {evidence.goal_title}",
            f"- Final status: {evidence.final_status}",
            f"- Strategy: {evidence.strategy_used}",
            "- Required gates: "
            f"{evidence.gate_summary.passed}/{evidence.gate_summary.required} passed",
            f"- Blocking review findings: {evidence.review_summary.blocking_findings}",
            "- Evidence validation: "
            f"{'valid' if evidence.validation.valid else 'invalid'}",
            "",
            "## Run Metrics",
            f"- Duration: {_format_duration(evidence.usage_summary.duration_ms)}",
            "- Tokens: "
            f"input {_format_int(evidence.usage_summary.input_tokens)} / "
            f"output {_format_int(evidence.usage_summary.output_tokens)} / "
            f"total {_format_int(evidence.usage_summary.total_tokens)}"
            f"{' (estimated)' if evidence.usage_summary.estimated else ''}",
            f"- Estimated cost: {_format_cost(evidence.usage_summary.estimated_cost_usd)}",
            "",
            "## Evidence Files",
        ]
        if evidence.evidence_files:
            lines.extend(
                f"- {item.type}: `{item.path}` ({item.sha256})"
                for item in evidence.evidence_files
            )
        else:
            lines.append("- No patch file was produced in the fake/demo run.")
        if evidence.validation.errors:
            lines.extend(["", "## Evidence Validation"])
            lines.extend(f"- {error}" for error in evidence.validation.errors)
        lines.extend(
            [
                "",
                "## Goal Satisfaction",
                f"- Verdict: {evidence.goal_satisfaction.verdict}",
                f"- Satisfied criteria: {evidence.goal_satisfaction.satisfied}",
                f"- Not satisfied criteria: {evidence.goal_satisfaction.not_satisfied}",
                f"- Uncertain criteria: {evidence.goal_satisfaction.uncertain}",
            ]
        )
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report


def _patch_has_changes(path: Path) -> bool:
    content = path.read_text(encoding="utf-8", errors="replace")
    return (
        "diff --git " in content
        or "\n--- " in content
        or content.startswith("--- ")
        or "GIT binary patch" in content
    )


def _goal_satisfaction_summary(
    report: GoalSatisfactionReportData | None,
) -> GoalSatisfactionSummary:
    if report is None:
        return GoalSatisfactionSummary(verdict="satisfied")
    return GoalSatisfactionSummary(
        verdict=report.verdict,
        satisfied=sum(
            1 for result in report.criterion_results if result.status == "satisfied"
        ),
        not_satisfied=sum(
            1 for result in report.criterion_results if result.status == "not_satisfied"
        ),
        uncertain=sum(
            1 for result in report.criterion_results if result.status == "uncertain"
        ),
    )


def _acceptance_results(
    gate_report: GateReportData,
    goal_satisfaction: GoalSatisfactionReportData | None,
    *,
    failed: bool,
) -> list[AcceptanceCoverage]:
    if goal_satisfaction is not None:
        return [
            AcceptanceCoverage(
                criterion_id=result.criterion_id,
                status=_goal_result_to_acceptance_status(result.status),
                evidence=result.evidence,
            )
            for result in goal_satisfaction.criterion_results
        ]
    return gate_report.acceptance_coverage or [
        AcceptanceCoverage(
            criterion_id="AC001",
            status="passed" if not failed else "failed",
            evidence=["05_gate_report.yaml"],
        )
    ]


def _goal_result_to_acceptance_status(status: str) -> Literal["passed", "failed", "manual"]:
    if status == "satisfied":
        return "passed"
    if status == "uncertain":
        return "manual"
    return "failed"


def _artifact_usages(run_dir: Path) -> list[WorkerUsage]:
    paths = [
        *sorted((run_dir / "tasks").glob("*/worker_result.yaml")),
        *sorted((run_dir / "repairs").glob("*/repair_result.yaml")),
    ]
    usages: list[WorkerUsage] = []
    for path in paths:
        if usage := _usage_from_artifact(path):
            usages.append(usage)
    return usages


def _tool_result_artifacts(run_dir: Path, result_path: Path) -> list[Path]:
    payload = load_yaml(result_path.read_text(encoding="utf-8"))
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return []
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    paths: list[Path] = []
    for value in artifacts:
        if not isinstance(value, str):
            continue
        path = (run_dir / value).resolve()
        try:
            path.relative_to(run_dir.resolve())
        except ValueError:
            continue
        if path.exists() and path.is_file():
            paths.append(path)
    return paths


def _tool_artifact_type(path: Path) -> str:
    name = path.name
    suffix = path.suffix.lower()
    if name == "image_asset_request.json":
        return "image_asset_request"
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "image_asset"
    if "screenshot" in name:
        return "tool_screenshot"
    if "console" in name:
        return "tool_console"
    if "summary" in name:
        return "tool_summary"
    return "tool_artifact"


def _usage_from_artifact(path: Path) -> WorkerUsage | None:
    payload = load_yaml(path.read_text(encoding="utf-8"))
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return WorkerUsage.model_validate(usage)


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "unknown"
    return f"{duration_ms} ms"


def _format_int(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def _format_cost(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.6f}"
