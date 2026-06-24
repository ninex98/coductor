"""Evidence bundle and report generation."""

from __future__ import annotations

from pathlib import Path

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    AcceptanceCoverage,
    EvidenceBundleData,
    EvidenceFile,
    GateReportData,
    GateSummary,
    PullRequestInfo,
    ReviewReportData,
    ReviewSummary,
    Rollback,
)
from coductor.domain.enums import ExecutionStrategy


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
    ) -> EvidenceBundleData:
        required = [gate for gate in gate_report.gates if gate.required]
        passed = [gate for gate in required if gate.status == "passed"]
        failed = [gate for gate in required if gate.status != "passed"]
        evidence_files: list[EvidenceFile] = []
        patch_path = run_dir / "tasks/T001/patch.diff"
        if patch_path.exists():
            evidence_files.append(
                EvidenceFile(
                    type="patch",
                    path="tasks/T001/patch.diff",
                    sha256=file_sha256(patch_path),
                )
            )
        final_status = (
            "ready_for_human_review"
            if not failed and review.blocking_findings == 0
            else "human_required"
        )
        return EvidenceBundleData(
            goal_title=goal_title,
            final_status=final_status,
            strategy_used=strategy,
            base_commit=gate_report.base_commit,
            head_commit=gate_report.head_commit,
            completed_tasks=completed_tasks,
            acceptance_results=gate_report.acceptance_coverage
            or [
                AcceptanceCoverage(
                    criterion_id="AC001",
                    status="passed" if not failed else "failed",
                    evidence=["05_gate_report.yaml"],
                )
            ],
            gate_summary=GateSummary(
                required=len(required),
                passed=len(passed),
                failed=len(failed),
            ),
            review_summary=ReviewSummary(blocking_findings=review.blocking_findings),
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
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report
