from __future__ import annotations

from pathlib import Path

import pytest

from coductor.artifacts.models import (
    ArtifactEnvelope,
    GateReportData,
    GoalCriterionResult,
    GoalData,
    GoalSatisfactionReportData,
    Producer,
    RepairRequestData,
    ToolResultData,
    VerificationPlanData,
    VerificationPlanItem,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ProducerKind,
    VerificationType,
)
from coductor.storage.database import Database
from coductor.web.read_service import ConsoleReadError, ConsoleReadService
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.state import WorkflowState


def _write_goal(run_dir: Path, run_id: str) -> None:
    repo = ArtifactRepository(run_dir)
    artifact = ArtifactEnvelope[GoalData](
        artifact_type=ArtifactType.GOAL,
        artifact_id="art_goal_00000000000000000000000001",
        run_id=run_id,
        revision=1,
        status=ArtifactStatus.ACCEPTED,
        created_at="2026-06-24T00:00:00Z",
        producer=Producer(kind=ProducerKind.HUMAN, name="cli-user"),
        inputs=[],
        data=GoalData(
            title="修复示例函数",
            raw_request="修复示例函数",
            goal_type="bugfix",
            requested_mode=ExecutionMode.AUTO,
        ),
    )
    repo.write("00_goal.yaml", artifact)


def _seed_run(root: Path, run_id: str = "run_abc") -> Path:
    run_dir = root / ".coductor" / "runs" / run_id
    run_dir.mkdir(parents=True)
    _write_goal(run_dir, run_id)
    db = Database(root / ".coductor" / "coductor.sqlite3")
    db.upsert_run(run_id, "running", run_dir.as_posix(), "2026-06-24T00:00:00Z")
    db.add_event(run_id, "collect_goal", "accepted user goal", "2026-06-24T00:00:01Z")
    WorkflowCheckpointStore(db, root / ".coductor" / "runs").save(
        WorkflowState(
            run_id=run_id,
            status="running",
            current_stage="dispatch_tasks",
            run_dir=run_dir.as_posix(),
            last_error=None,
        ),
        "2026-06-24T00:00:02Z",
    )
    (run_dir / "delivery-report.md").write_text("# Report\n", encoding="utf-8")
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "unit_tests.stdout.log").write_text("passed\n", encoding="utf-8")
    return run_dir


def test_console_read_service_lists_runs_with_checkpoint(tmp_path: Path) -> None:
    _seed_run(tmp_path, "run_old")
    _seed_run(tmp_path, "run_new")
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    db.update_run_status("run_new", "ready_for_human_review", "2026-06-24T00:01:00Z")
    service = ConsoleReadService(tmp_path)

    runs = service.list_runs()

    assert [run.run_id for run in runs] == ["run_new", "run_old"]
    assert runs[0].status == "ready_for_human_review"
    assert runs[0].current_stage == "dispatch_tasks"


def test_console_read_service_reads_artifact_detail(tmp_path: Path) -> None:
    _seed_run(tmp_path)
    service = ConsoleReadService(tmp_path)

    artifacts = service.list_artifacts("run_abc")
    detail = service.get_artifact("run_abc", "00_goal.yaml")

    assert [artifact.path for artifact in artifacts] == ["00_goal.yaml"]
    assert detail.path == "00_goal.yaml"
    assert detail.artifact_type == "goal"
    assert detail.parsed_yaml["data"]["title"] == "修复示例函数"
    assert "artifact_type: goal" in detail.raw_text
    assert detail.truncated is False


def test_console_read_service_rejects_unsafe_artifact_path(tmp_path: Path) -> None:
    _seed_run(tmp_path)
    service = ConsoleReadService(tmp_path)

    with pytest.raises(ConsoleReadError):
        service.get_artifact("run_abc", "../coductor.yaml")


def test_console_read_service_reads_events_report_and_logs(tmp_path: Path) -> None:
    _seed_run(tmp_path)
    service = ConsoleReadService(tmp_path)

    assert service.get_events("run_abc")[0].stage == "collect_goal"
    assert service.get_report("run_abc") == "# Report\n"
    assert service.get_log("run_abc", "logs/unit_tests.stdout.log").raw_text == "passed\n"


def test_console_read_service_summarizes_goal_loop(tmp_path: Path) -> None:
    run_dir = _seed_run(tmp_path)
    repo = ArtifactRepository(run_dir)
    tool_result_path = "tool_runs/browser_smoke/tool_result.yaml"
    repo.write(
        "03_verification_plan.yaml",
        ArtifactEnvelope[VerificationPlanData](
            artifact_type=ArtifactType.VERIFICATION_PLAN,
            artifact_id="art_verification_plan_abc",
            run_id="run_abc",
            revision=1,
            status=ArtifactStatus.READY,
            created_at="2026-06-24T00:00:03Z",
            producer=Producer(kind=ProducerKind.SYSTEM, name="verification-planner"),
            inputs=[],
            data=VerificationPlanData(
                items=[
                    VerificationPlanItem(
                        id="VP001",
                        criterion_id="AC001",
                        description="浏览器冒烟验证通过",
                        verification=VerificationType.AUTOMATED,
                        tool="quality_gate+tool_check",
                        evidence_paths=["05_gate_report.yaml", tool_result_path],
                    )
                ]
            ),
        ),
    )
    repo.write(
        "05_gate_report.yaml",
        ArtifactEnvelope[GateReportData](
            artifact_type=ArtifactType.GATE_REPORT,
            artifact_id="art_gate_report_abc",
            run_id="run_abc",
            revision=1,
            status=ArtifactStatus.PASSED,
            created_at="2026-06-24T00:00:04Z",
            producer=Producer(kind=ProducerKind.TOOL, name="gate-runner"),
            inputs=[],
            data=GateReportData(
                base_commit="base",
                head_commit="head",
                required_gates_passed=True,
                next_action="review",
            ),
        ),
    )
    repo.write(
        tool_result_path,
        ArtifactEnvelope[ToolResultData](
            artifact_type=ArtifactType.TOOL_RESULT,
            artifact_id="art_tool_result_abc",
            run_id="run_abc",
            revision=1,
            status=ArtifactStatus.PASSED,
            created_at="2026-06-24T00:00:05Z",
            producer=Producer(kind=ProducerKind.TOOL, name="tool-verification-service"),
            inputs=[],
            data=ToolResultData(
                tool_run_id="browser_smoke",
                check_id="browser_smoke",
                tool="browser",
                status="passed",
                command="generated-browser-smoke",
                stdout_path="tool_runs/browser_smoke/stdout.log",
                stderr_path="tool_runs/browser_smoke/stderr.log",
                artifacts=["tool_runs/browser_smoke/browser_screenshot.png"],
                evidence_paths=[tool_result_path],
            ),
        ),
    )
    repo.write(
        "07_goal_satisfaction.yaml",
        ArtifactEnvelope[GoalSatisfactionReportData](
            artifact_type=ArtifactType.GOAL_SATISFACTION_REPORT,
            artifact_id="art_goal_satisfaction_abc",
            run_id="run_abc",
            revision=1,
            status=ArtifactStatus.PASSED,
            created_at="2026-06-24T00:00:06Z",
            producer=Producer(kind=ProducerKind.SYSTEM, name="goal-satisfaction-evaluator"),
            inputs=[],
            data=GoalSatisfactionReportData(
                verdict="satisfied",
                criterion_results=[
                    GoalCriterionResult(
                        criterion_id="AC001",
                        status="satisfied",
                        evidence=["05_gate_report.yaml", tool_result_path],
                        reason="required quality gates and tool checks passed",
                    )
                ],
            ),
        ),
    )
    repo.write(
        "repairs/repair_001/repair_request.yaml",
        ArtifactEnvelope[RepairRequestData](
            artifact_type=ArtifactType.REPAIR_REQUEST,
            artifact_id="art_repair_request_abc",
            run_id="run_abc",
            revision=1,
            status=ArtifactStatus.READY,
            created_at="2026-06-24T00:00:07Z",
            producer=Producer(kind=ProducerKind.SYSTEM, name="repair-service"),
            inputs=[],
            data=RepairRequestData(
                repair_id="repair_001",
                target_task_id="T001",
                resume_thread_id=None,
                attempt=1,
                max_attempts=2,
                reason="goal_not_satisfied",
                failed_gates=[],
                failure_fingerprints=[],
                missing_criteria=["AC001"],
            ),
        ),
    )
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs").save(
        WorkflowState(
            run_id="run_abc",
            status="running",
            current_stage="evaluate_goal_satisfaction",
            run_dir=run_dir.as_posix(),
            goal_iteration=2,
            satisfaction_repair_attempts=1,
        ),
        "2026-06-24T00:00:08Z",
    )
    service = ConsoleReadService(tmp_path)

    detail = service.get_run("run_abc")

    assert detail.goal_loop is not None
    assert detail.goal_loop.verdict == "satisfied"
    assert detail.goal_loop.satisfied == 1
    assert detail.goal_loop.goal_iteration == 2
    assert detail.goal_loop.criteria[0].criterion_id == "AC001"
    assert detail.goal_loop.tools[0].check_id == "browser_smoke"
    assert detail.goal_loop.repairs[0].reason == "goal_not_satisfied"
