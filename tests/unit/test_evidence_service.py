from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import (
    GateReportData,
    GateResultData,
    ReviewReportData,
)
from coductor.domain.enums import ExecutionStrategy
from coductor.services.evidence_service import EvidenceCompletenessValidator, EvidenceService


def _gate_report(*, passed: bool = True) -> GateReportData:
    return GateReportData(
        base_commit="base",
        head_commit="head",
        gates=[
            GateResultData(
                id="unit_tests",
                required=True,
                status="passed" if passed else "failed",
                command="pytest",
                exit_code=0 if passed else 1,
                duration_ms=1,
                stdout_path="logs/stdout.txt",
                stderr_path="logs/stderr.txt",
            )
        ],
        required_gates_passed=passed,
        next_action="review" if passed else "repair",
    )


def _review(*, blocking_findings: int = 0) -> ReviewReportData:
    return ReviewReportData(
        reviewer_thread_id="thread_review",
        reviewed_base_commit="base",
        reviewed_head_commit="head",
        findings=[],
        blocking_findings=blocking_findings,
        verdict="fail" if blocking_findings else "pass",
        requires_repair=blocking_findings > 0,
    )


def test_evidence_is_not_ready_when_review_has_blocking_finding(tmp_path: Path) -> None:
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/file b/file\n", encoding="utf-8")

    evidence = EvidenceService().build(
        run_dir=tmp_path,
        goal_title="demo",
        strategy=ExecutionStrategy.SOLO,
        gate_report=_gate_report(passed=True),
        review=_review(blocking_findings=1),
        completed_tasks=["T001"],
    )

    assert evidence.final_status == "human_required"


def test_evidence_requires_patch_and_gate_report() -> None:
    evidence = EvidenceService().build(
        run_dir=Path("/tmp/non-existent-coductor-run"),
        goal_title="demo",
        strategy=ExecutionStrategy.SOLO,
        gate_report=_gate_report(passed=True),
        review=_review(blocking_findings=0),
        completed_tasks=["T001"],
    )

    result = EvidenceCompletenessValidator().validate(evidence)

    assert not result.valid
    assert "patch" in result.errors[0]


def test_evidence_rejects_placeholder_patch(tmp_path: Path) -> None:
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("# fake backend did not produce a patch\n", encoding="utf-8")

    evidence = EvidenceService().build(
        run_dir=tmp_path,
        goal_title="demo",
        strategy=ExecutionStrategy.SOLO,
        gate_report=_gate_report(passed=True),
        review=_review(blocking_findings=0),
        completed_tasks=["T001"],
    )

    assert evidence.final_status == "human_required"
    assert "patch evidence has no changes" in evidence.validation.errors
