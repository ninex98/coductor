"""Independent review and evidence delivery."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    EvidenceBundleData,
    Finding,
    GateReportData,
    GoalData,
    GoalSatisfactionReportData,
    Producer,
    ReviewReportData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import CodingBackend, WorkerRequest
from coductor.config.models import CoductorConfig
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionStrategy,
    ProducerKind,
    SandboxMode,
)
from coductor.prompts.renderer import PromptSection, render_worker_prompt
from coductor.services.evidence_service import EvidenceService
from coductor.services.usage import usage_from_backend
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class ReviewDeliveryService:
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

    def review(
        self,
        repo: ArtifactRepository,
        run_id: str,
        gate_report: ArtifactEnvelope[GateReportData],
        completed_task_ids: list[str],
    ) -> ArtifactEnvelope[ReviewReportData]:
        patch_paths = [
            f"tasks/{task_id}/patch.diff"
            for task_id in completed_task_ids
            if (repo.root / f"tasks/{task_id}/patch.diff").exists()
        ]
        satisfaction_paths = (
            ["07_goal_satisfaction.yaml"]
            if (repo.root / "07_goal_satisfaction.yaml").exists()
            else []
        )
        request = WorkerRequest(
            worker_id="worker_review",
            role="reviewer",
            prompt=render_worker_prompt(
                "reviewer",
                [
                    "02_spec.yaml",
                    "03_verification_plan.yaml",
                    "05_gate_report.yaml",
                    *satisfaction_paths,
                    *patch_paths,
                ],
                "independently review the verified change",
                sections=_review_prompt_sections(gate_report, completed_task_ids, patch_paths),
            ),
            workspace_path=self.root.as_posix(),
            sandbox=SandboxMode.READ_ONLY,
        )
        started_at = time.monotonic()
        handle = self.backend.start_worker(request)
        result = self.backend.continue_worker(handle, request)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        data = parse_review_summary(
            result.summary,
            reviewer_thread_id=result.thread_id,
            reviewed_base_commit=gate_report.data.base_commit,
            reviewed_head_commit=gate_report.data.head_commit,
        )
        data.usage = usage_from_backend(
            result.usage,
            prompt=request.prompt,
            summary=result.summary,
            duration_ms=duration_ms,
        )
        envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REVIEW_REPORT,
            artifact_id_prefix="art_review",
            status=ArtifactStatus.PASSED if data.verdict == "pass" else ArtifactStatus.FAILED,
            producer=Producer(kind=ProducerKind.MODEL, name="independent-reviewer"),
            data=data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for("05_gate_report.yaml", gate_report)
                )
            ],
        )
        repo.write("06_review.yaml", envelope)
        return envelope

    def evidence(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
        gate_report: ArtifactEnvelope[GateReportData],
        review: ArtifactEnvelope[ReviewReportData],
        strategy: ExecutionStrategy,
        completed_task_ids: list[str],
        goal_satisfaction: ArtifactEnvelope[GoalSatisfactionReportData] | None = None,
    ) -> ArtifactEnvelope[EvidenceBundleData]:
        service = EvidenceService()
        data = service.build(
            run_dir=repo.root,
            goal_title=goal.data.title,
            strategy=strategy,
            gate_report=gate_report.data,
            review=review.data,
            completed_tasks=completed_task_ids,
            goal_satisfaction=(
                goal_satisfaction.data if goal_satisfaction is not None else None
            ),
        )
        envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.EVIDENCE_BUNDLE,
            artifact_id_prefix="art_evidence",
            status=(
                ArtifactStatus.READY_FOR_HUMAN_REVIEW
                if data.final_status == "ready_for_human_review"
                else ArtifactStatus.HUMAN_REQUIRED
            ),
            producer=Producer(kind=ProducerKind.SYSTEM, name="delivery-manager"),
            data=data,
            inputs=[
                ArtifactInput.model_validate(repo.input_for("05_gate_report.yaml", gate_report)),
                ArtifactInput.model_validate(repo.input_for("06_review.yaml", review)),
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
        repo.write("07_evidence.yaml", envelope)
        service.write_report(repo.root, data)
        return envelope


def parse_review_summary(
    summary: str,
    *,
    reviewer_thread_id: str,
    reviewed_base_commit: str,
    reviewed_head_commit: str,
) -> ReviewReportData:
    verdict: Literal["pass", "fail"] = "pass"
    blocking = False
    findings: list[Finding] = []
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if lowered.startswith("verdict:"):
            value = line.split(":", 1)[1].strip().lower()
            verdict = "fail" if value == "fail" else "pass"
        elif lowered.startswith("blocking:"):
            value = line.split(":", 1)[1].strip().lower()
            blocking = value in {"true", "yes", "1", "blocking"}
        elif lowered.startswith("finding:"):
            findings.append(_parse_finding(line.split(":", 1)[1].strip(), len(findings) + 1))
    blocking_findings = len(findings) if blocking else 0
    requires_repair = verdict == "fail" or blocking_findings > 0
    if requires_repair:
        verdict = "fail"
    return ReviewReportData(
        reviewer_thread_id=reviewer_thread_id,
        reviewed_base_commit=reviewed_base_commit,
        reviewed_head_commit=reviewed_head_commit,
        findings=findings,
        blocking_findings=blocking_findings,
        verdict=verdict,
        requires_repair=requires_repair,
    )


def _review_prompt_sections(
    gate_report: ArtifactEnvelope[GateReportData],
    completed_task_ids: list[str],
    patch_paths: list[str],
) -> list[PromptSection]:
    gate_items = [
        (
            f"{gate.id}: status={gate.status}, required={gate.required}, "
            f"command={gate.command}, stdout={gate.stdout_path}, stderr={gate.stderr_path}"
        )
        for gate in gate_report.data.gates
    ]
    return [
        PromptSection(
            "Review Scope",
            [
                f"completed_tasks: {', '.join(completed_task_ids) or '(none)'}",
                f"patches: {', '.join(patch_paths) or '(none)'}",
                (
                    "Check 07_goal_satisfaction.yaml when present; do not assume gates "
                    "alone prove the goal."
                ),
            ],
        ),
        PromptSection("Gate Results", gate_items or ["No quality gates were configured."]),
        PromptSection(
            "Required Reviewer Output",
            [
                "VERDICT: pass|fail",
                "BLOCKING: true|false",
                (
                    "FINDING: severity=high; category=correctness; file=path; "
                    "line=1; description=...; recommendation=..."
                ),
            ],
        ),
    ]


def _parse_finding(payload: str, index: int) -> Finding:
    fields = _parse_semicolon_fields(payload)
    line_value = fields.get("line")
    return Finding(
        id=fields.get("id", f"F{index:03d}"),
        severity=_severity(fields.get("severity", "medium")),
        category=fields.get("category", "general"),
        file=fields.get("file"),
        line=int(line_value) if line_value and line_value.isdigit() else None,
        description=fields.get("description", "Reviewer reported an unspecified issue."),
        recommendation=fields.get("recommendation", "Inspect the review output and repair."),
    )


def _parse_semicolon_fields(payload: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in payload.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _severity(value: str) -> Literal["low", "medium", "high", "critical"]:
    normalized = value.strip().lower()
    severity_map: dict[str, Literal["low", "medium", "high", "critical"]] = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "critical": "critical",
    }
    return severity_map.get(normalized, "medium")
