"""Independent review and evidence delivery."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    EvidenceBundleData,
    Finding,
    GateReportData,
    GoalData,
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
from coductor.prompts.renderer import render_worker_prompt
from coductor.services.evidence_service import EvidenceService
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
        request = WorkerRequest(
            worker_id="worker_review",
            role="reviewer",
            prompt=render_worker_prompt(
                "reviewer",
                ["02_spec.yaml", "05_gate_report.yaml", *patch_paths],
                "independently review the verified change",
            ),
            workspace_path=self.root.as_posix(),
            sandbox=SandboxMode.READ_ONLY,
        )
        handle = self.backend.start_worker(request)
        result = self.backend.continue_worker(handle, request)
        data = parse_review_summary(
            result.summary,
            reviewer_thread_id=result.thread_id,
            reviewed_base_commit=gate_report.data.base_commit,
            reviewed_head_commit=gate_report.data.head_commit,
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
    ) -> ArtifactEnvelope[EvidenceBundleData]:
        service = EvidenceService()
        data = service.build(
            run_dir=repo.root,
            goal_title=goal.data.title,
            strategy=strategy,
            gate_report=gate_report.data,
            review=review.data,
            completed_tasks=completed_task_ids,
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
