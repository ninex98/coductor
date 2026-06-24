from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from coductor.cli import app
from coductor.storage.database import Database


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
    ("command", "status"),
    [
        ("approve", "approved"),
        ("pause", "paused"),
        ("stop", "stopped"),
        ("verify", "verification_requested"),
        ("review", "review_requested"),
    ],
)
def test_cli_control_commands_update_status_and_log_event(
    command: str,
    status: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, [command, "run_abc"])

    assert result.exit_code == 0
    assert f"Stage: {command}" in result.output
    assert f"Status: {status}" in result.output
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    row = db.get_run("run_abc")
    assert row is not None
    assert row["status"] == status
    events = db.list_events("run_abc")
    assert events[-1]["stage"] == command
