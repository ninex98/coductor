from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coductor import cli
from coductor.cli import app
from coductor.domain.enums import RunStatus
from coductor.domain.models import RunResult
from coductor.exceptions import BackendUnavailableError
from coductor.storage.database import Database
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.state import WorkflowState


def test_cli_root_help_is_bilingual_and_actionable() -> None:
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Coductor / 确定性 AI Coding 工作流引擎" in result.output
    assert "Quick start / 快速开始" in result.output
    assert "init       初始化当前项目 / Initialize a project" in result.output
    assert "run        运行研发目标 / Run a coding goal" in result.output
    assert "artifacts  查看产物列表 / List run artifacts" in result.output
    assert "--version" in result.output


def test_cli_without_command_shows_quick_start() -> None:
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Quick start / 快速开始" in result.output
    assert "coductor init" in result.output
    assert "coductor run \"修复示例函数并补充测试\" --backend fake" in result.output


def test_cli_version_option() -> None:
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "coductor 0.1.0" in result.output


def test_cli_run_failure_uses_recovery_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    def raise_backend_error(*args, **kwargs):
        raise BackendUnavailableError(
            "Codex CLI executable not found: codex",
            stage="backend",
            recoverable=True,
            next_command="coductor doctor",
        )

    monkeypatch.setattr(cli, "run_goal", raise_backend_error)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["run", "修复问题"])

    assert result.exit_code == 1
    assert "阶段: backend" in result.output
    assert "下一步: coductor doctor" in result.output
    assert "Codex CLI executable not found: codex" in result.output
    assert "Traceback" not in result.output


def test_cli_run_prints_progress_and_next_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / ".coductor" / "runs" / "run_abc"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.html").write_text(
        "<script type='module'></script>",
        encoding="utf-8",
    )
    run_dir.mkdir(parents=True)

    def fake_run(self, goal, *, mode=None, resume_run_id=None):
        self._progress("collect_goal", "accepted user goal")
        self._progress("dispatch_tasks", "dispatch T001")
        return RunResult(
            run_id="run_abc",
            status=RunStatus.READY_FOR_HUMAN_REVIEW,
            run_dir=run_dir.as_posix(),
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.RunService, "run", fake_run)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["run", "创建网页小游戏"])

    assert result.exit_code == 0
    assert "[collect_goal] accepted user goal" in result.output
    assert "[dispatch_tasks] dispatch T001" in result.output
    assert "生成文件:" in result.output
    assert "src/index.html" in result.output
    assert "启动预览:" in result.output
    assert "python3 -m http.server 4173 --bind 127.0.0.1 --directory src" in result.output


def test_cli_init_empty_project_has_no_default_python_gates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["init"])

    assert result.exit_code == 0
    config = (tmp_path / "coductor.yaml").read_text(encoding="utf-8")
    assert "quality_gates: []" in config
    assert "pytest -q" not in config
    assert "ruff check ." not in config


def test_cli_status_json_includes_checkpoint_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = _seed_run(tmp_path)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs").save(
        WorkflowState(
            run_id="run_abc",
            status=RunStatus.RUNNING,
            current_stage="dispatch_tasks",
            run_dir=run_dir.as_posix(),
            completed_task_ids=["T001"],
            stale_artifacts=["contracts/generated.schema.json: sha256 mismatch"],
        ),
        "2026-06-24T00:00:02Z",
    )
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["status", "run_abc", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["run"]["run_id"] == "run_abc"
    assert payload["run"]["status"] == "running"
    assert payload["checkpoint"]["current_stage"] == "dispatch_tasks"
    assert payload["checkpoint"]["completed_task_ids"] == ["T001"]
    assert payload["checkpoint"]["stale_artifacts"] == [
        "contracts/generated.schema.json: sha256 mismatch"
    ]


def _seed_run(root: Path, run_id: str = "run_abc") -> Path:
    run_dir = root / ".coductor" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "00_goal.yaml").write_text("artifact_type: goal\n", encoding="utf-8")
    (run_dir / "tasks" / "T001").mkdir(parents=True)
    (run_dir / "tasks" / "T001" / "task.yaml").write_text(
        "artifact_type: task\n",
        encoding="utf-8",
    )
    db = Database(root / ".coductor" / "coductor.sqlite3")
    db.upsert_run(
        run_id,
        "ready_for_human_review",
        run_dir.as_posix(),
        "2026-06-24T00:00:00Z",
    )
    db.add_event(
        run_id,
        "dispatch_tasks",
        "dispatch T001",
        "2026-06-24T00:00:01Z",
    )
    return run_dir


def test_cli_artifacts_lists_yaml_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["artifacts", "run_abc"])

    assert result.exit_code == 0
    assert "Run ID: run_abc" in result.output
    assert "Stage: artifacts" in result.output
    assert "00_goal.yaml" in result.output
    assert "tasks/T001/task.yaml" in result.output


def test_cli_artifacts_includes_checkpoint_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = _seed_run(tmp_path)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs").save(
        WorkflowState(
            run_id="run_abc",
            status=RunStatus.RUNNING,
            current_stage="dispatch_tasks",
            run_dir=run_dir.as_posix(),
            completed_task_ids=["T001"],
        ),
        "2026-06-24T00:00:02Z",
    )
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["artifacts", "run_abc"])

    assert result.exit_code == 0
    assert "Current stage: dispatch_tasks" in result.output
    assert "Completed tasks: T001" in result.output
    assert "00_goal.yaml" in result.output


def test_cli_logs_lists_run_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["logs", "run_abc"])

    assert result.exit_code == 0
    assert "Run ID: run_abc" in result.output
    assert "Stage: logs" in result.output
    assert "dispatch_tasks" in result.output
    assert "dispatch T001" in result.output


def test_cli_logs_filters_by_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    db.add_event(
        "run_abc",
        "run_quality_gates",
        "gate passed",
        "2026-06-24T00:00:02Z",
    )
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["logs", "run_abc", "--stage", "dispatch_tasks"])

    assert result.exit_code == 0
    assert "dispatch_tasks" in result.output
    assert "dispatch T001" in result.output
    assert "run_quality_gates" not in result.output
    assert "gate passed" not in result.output


def test_cli_logs_json_respects_stage_filter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    db.add_event(
        "run_abc",
        "run_quality_gates",
        "gate passed",
        "2026-06-24T00:00:02Z",
    )
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(
        app,
        ["logs", "run_abc", "--stage", "dispatch_tasks", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["run_id"] == "run_abc"
    assert payload["events"] == [
        {
            "stage": "dispatch_tasks",
            "message": "dispatch T001",
            "created_at": "2026-06-24T00:00:01Z",
        }
    ]


def test_cli_logs_tail_limits_recent_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    db.add_event(
        "run_abc",
        "run_quality_gates",
        "gate passed",
        "2026-06-24T00:00:02Z",
    )
    db.add_event(
        "run_abc",
        "prepare_evidence",
        "evidence ready",
        "2026-06-24T00:00:03Z",
    )
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["logs", "run_abc", "--tail", "2", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert [event["stage"] for event in payload["events"]] == [
        "run_quality_gates",
        "prepare_evidence",
    ]


def test_cli_explain_summarizes_recoverability_and_next_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["explain", "run_abc"])

    assert result.exit_code == 0
    assert "Run ID: run_abc" in result.output
    assert "Stage: explain" in result.output
    assert "Recoverable: yes" in result.output
    assert "Next command: coductor report run_abc" in result.output


def test_cli_explain_includes_checkpoint_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = _seed_run(tmp_path)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs").save(
        WorkflowState(
            run_id="run_abc",
            status=RunStatus.HUMAN_REQUIRED,
            current_stage="dispatch_tasks",
            raw_goal="先定义 schema 再实现",
            run_dir=run_dir.as_posix(),
            artifacts={
                "task_T001": "tasks/T001/task.yaml",
                "worker_result_T001": "tasks/T001/worker_result.yaml",
            },
            completed_task_ids=["T001"],
            stale_artifacts=["contracts/generated.schema.json: sha256 mismatch"],
            last_error="stale artifact lineage detected",
        ),
        "2026-06-24T00:00:02Z",
    )
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["explain", "run_abc"])

    assert result.exit_code == 0
    assert "Current stage: dispatch_tasks" in result.output
    assert "Completed tasks: T001" in result.output
    assert "Last error: stale artifact lineage detected" in result.output
    assert "Stale artifacts:" in result.output
    assert "contracts/generated.schema.json: sha256 mismatch" in result.output


def test_cli_missing_run_failure_includes_recovery_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    Database(tmp_path / ".coductor" / "coductor.sqlite3")
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["artifacts", "missing_run"])

    assert result.exit_code == 1
    assert "Run ID: missing_run" in result.output
    assert "Stage: artifacts" in result.output
    assert "Recoverable: yes" in result.output
    assert "Next command: coductor status" in result.output


@pytest.mark.parametrize(
    ("command", "initial_status", "status"),
    [
        ("approve", "human_required", "approved"),
        ("pause", "running", "paused"),
        ("stop", "running", "stopped"),
        ("verify", "ready_for_human_review", "verification_requested"),
        ("review", "ready_for_human_review", "review_requested"),
    ],
)
def test_cli_control_commands_update_status_and_log_event(
    command: str,
    initial_status: str,
    status: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    db.update_run_status("run_abc", initial_status, "2026-06-24T00:00:02Z")
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, [command, "run_abc"])

    assert result.exit_code == 0
    assert f"Stage: {command}" in result.output
    assert f"Status: {status}" in result.output
    row = db.get_run("run_abc")
    assert row is not None
    assert row["status"] == status
    events = db.list_events("run_abc")
    assert events[-1]["stage"] == command


def test_cli_pause_rejects_completed_run_without_changing_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["pause", "run_abc"])

    assert result.exit_code == 1
    assert "cannot pause run in status ready_for_human_review" in result.output
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    row = db.get_run("run_abc")
    assert row is not None
    assert row["status"] == "ready_for_human_review"


def test_cli_approve_rejects_ready_run_without_changing_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["approve", "run_abc"])

    assert result.exit_code == 1
    assert "cannot approve run in status ready_for_human_review" in result.output
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    row = db.get_run("run_abc")
    assert row is not None
    assert row["status"] == "ready_for_human_review"
