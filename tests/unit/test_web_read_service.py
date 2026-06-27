from __future__ import annotations

from pathlib import Path

import pytest

from coductor.artifacts.models import ArtifactEnvelope, GoalData, Producer
from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import ArtifactStatus, ArtifactType, ExecutionMode, ProducerKind
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
