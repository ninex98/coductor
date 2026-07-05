from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import (
    GateReportData,
    GateResultData,
    GoalCriterionResult,
    GoalSatisfactionReportData,
    ReviewReportData,
    WorkerUsage,
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
        usage=WorkerUsage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            duration_ms=3,
            estimated=False,
        ),
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


def test_evidence_rejects_unsatisfied_goal_report(tmp_path: Path) -> None:
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/file b/file\n", encoding="utf-8")

    evidence = EvidenceService().build(
        run_dir=tmp_path,
        goal_title="demo",
        strategy=ExecutionStrategy.SOLO,
        gate_report=_gate_report(passed=True),
        review=_review(blocking_findings=0),
        completed_tasks=["T001"],
        goal_satisfaction=GoalSatisfactionReportData(
            verdict="not_satisfied",
            criterion_results=[
                GoalCriterionResult(
                    criterion_id="AC001",
                    status="not_satisfied",
                    missing_evidence=["missing.txt"],
                    reason="planned evidence is missing",
                )
            ],
            missing_evidence=["missing.txt"],
            requires_repair=True,
        ),
    )

    assert evidence.final_status == "human_required"
    assert "goal satisfaction is not satisfied" in evidence.validation.errors


def test_evidence_acceptance_results_follow_goal_satisfaction_criteria(
    tmp_path: Path,
) -> None:
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/file b/file\n", encoding="utf-8")

    evidence = EvidenceService().build(
        run_dir=tmp_path,
        goal_title="demo",
        strategy=ExecutionStrategy.SOLO,
        gate_report=_gate_report(passed=True),
        review=_review(blocking_findings=0),
        completed_tasks=["T001"],
        goal_satisfaction=GoalSatisfactionReportData(
            verdict="uncertain",
            criterion_results=[
                GoalCriterionResult(
                    criterion_id="AC001",
                    status="satisfied",
                    evidence=["05_gate_report.yaml"],
                    reason="required quality gates passed",
                ),
                GoalCriterionResult(
                    criterion_id="AC002",
                    status="not_satisfied",
                    evidence=[],
                    missing_evidence=["tool_runs/example/tool_result.yaml"],
                    reason="planned evidence is missing",
                ),
                GoalCriterionResult(
                    criterion_id="AC003",
                    status="uncertain",
                    evidence=[],
                    reason="manual verification is required",
                ),
            ],
            missing_evidence=["tool_runs/example/tool_result.yaml"],
            requires_human=True,
        ),
    )

    assert [
        (item.criterion_id, item.status, item.evidence)
        for item in evidence.acceptance_results
    ] == [
        ("AC001", "passed", ["05_gate_report.yaml"]),
        ("AC002", "failed", []),
        ("AC003", "manual", []),
    ]


def test_evidence_summarizes_worker_and_review_usage(tmp_path: Path) -> None:
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/file b/file\n", encoding="utf-8")
    (tmp_path / "tasks/T001/worker_result.yaml").write_text(
        "\n".join(
            [
                "data:",
                "  usage:",
                "    input_tokens: 40",
                "    output_tokens: 12",
                "    total_tokens: 52",
                "    duration_ms: 20",
                "    estimated: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    service = EvidenceService()
    evidence = service.build(
        run_dir=tmp_path,
        goal_title="demo",
        strategy=ExecutionStrategy.SOLO,
        gate_report=_gate_report(passed=True),
        review=_review(blocking_findings=0),
        completed_tasks=["T001"],
    )
    report = service.write_report(tmp_path, evidence).read_text(encoding="utf-8")

    assert evidence.usage_summary.input_tokens == 50
    assert evidence.usage_summary.output_tokens == 17
    assert evidence.usage_summary.total_tokens == 67
    assert evidence.usage_summary.duration_ms == 23
    assert evidence.usage_summary.estimated is True
    assert "## Run Metrics" in report
    assert "Tokens: input 50 / output 17 / total 67 (estimated)" in report


def test_evidence_summarizes_repair_usage(tmp_path: Path) -> None:
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/file b/file\n", encoding="utf-8")
    repair = tmp_path / "repairs/R001/repair_result.yaml"
    repair.parent.mkdir(parents=True)
    repair.write_text(
        "\n".join(
            [
                "data:",
                "  usage:",
                "    input_tokens: 8",
                "    output_tokens: 2",
                "    total_tokens: 10",
                "    duration_ms: 5",
                "    estimated: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    evidence = EvidenceService().build(
        run_dir=tmp_path,
        goal_title="demo",
        strategy=ExecutionStrategy.SOLO,
        gate_report=_gate_report(passed=True),
        review=_review(blocking_findings=0),
        completed_tasks=["T001"],
    )

    assert evidence.usage_summary.input_tokens == 18
    assert evidence.usage_summary.output_tokens == 7
    assert evidence.usage_summary.total_tokens == 25
    assert evidence.usage_summary.duration_ms == 8
