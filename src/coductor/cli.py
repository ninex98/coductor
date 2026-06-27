"""Coductor command line interface."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Annotated, Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    ExecutionPlanData,
    GateReportData,
    GoalData,
    SpecificationData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import dump_yaml
from coductor.backends.capabilities import describe_backend_capability, effective_backend_provider
from coductor.backends.factory import create_backend, is_codex_sdk_available, resolve_codex_bin
from coductor.config.loader import discover_config, load_config, write_config
from coductor.constants import CODUCTOR_DIR, VERSION
from coductor.domain.enums import ArtifactType, ExecutionMode, ExecutionStrategy, RunStatus
from coductor.exceptions import CoductorError
from coductor.services.release_service import ReleaseService
from coductor.services.report_service import CONTROL_STATUS, ReportService, RunReportError
from coductor.services.review_delivery_service import ReviewDeliveryService
from coductor.services.run_service import RUN_LOCK_STALE_AFTER_SECONDS, RunService
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.storage.database import Database
from coductor.web.server import ServeOptionsError, serve_console
from coductor.workflow.artifact_writer import WorkflowArtifactWriter
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.langgraph_checkpoint import LangGraphCheckpointStore
from coductor.workflow.state import WorkflowState

try:  # pragma: no cover - fallback keeps local smoke checks useful without dependencies
    import typer
except ModuleNotFoundError:  # pragma: no cover
    typer = None  # type: ignore[assignment]

try:  # pragma: no cover
    from rich.console import Console
    from rich.table import Table
except ModuleNotFoundError:  # pragma: no cover
    Console = None  # type: ignore[misc, assignment]
    Table = None  # type: ignore[misc, assignment]


console = Console() if Console is not None else None
CLI_BANNER = r"""
       __                         CODUCTOR
      /  \__                      AI Coding Workflow Engine
     /      \___
    /  /\       \                 From goal to verified change.
   /__/  \___    \
          /  \____\               init    prepare project
         /__/  /__/               run     verified workflow
                                   status  inspect run state
"""

CLI_HELP = """
CODUCTOR / 确定性 AI Coding 工作流引擎

From goal to verified change. 把自然语言研发目标转成可审计、可恢复、可验证的工程流程。

Quick start / 快速开始:
  coductor init
  coductor doctor
  coductor run "修复示例函数并补充测试" --backend fake
  coductor status <RUN_ID>
  coductor artifacts <RUN_ID>
  coductor logs <RUN_ID>
  coductor explain <RUN_ID>
  coductor report <RUN_ID>
  coductor release <RUN_ID>
  coductor serve

Common commands / 常用命令:
  init       初始化当前项目 / Initialize a project
  run        运行研发目标 / Run a coding goal
  status     查看运行状态 / Show run status
  artifacts  查看产物列表 / List run artifacts
  logs       查看事件日志 / Show run event logs
  explain    解释状态和下一步 / Explain state and next command
  report     查看交付报告 / Show delivery report
  release    生成发布清单 / Generate release manifest
  serve      启动本地 Web 控制台 / Start local Web console
  doctor     检查安装与安全默认值 / Check installation and defaults
"""

if typer is not None:
    app: Any = typer.Typer(
        help=CLI_HELP,
        no_args_is_help=False,
        invoke_without_command=True,
        context_settings={"help_option_names": ["--help", "-h"]},
    )
else:  # pragma: no cover
    app = None


def _print(message: str) -> None:
    if console is not None:
        console.print(message, markup=False)
    else:
        print(message)


def _print_plain(message: str) -> None:
    print(message)


def print_quick_start() -> None:
    _print_plain(CLI_BANNER.strip())
    _print_plain("")
    _print(CLI_HELP.strip())


def _root(path: str | Path = ".") -> Path:
    return Path(path).resolve()


def _db(root: Path) -> Database:
    return Database(root / CODUCTOR_DIR / "coductor.sqlite3")


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _report_service(root: Path) -> ReportService:
    return ReportService(_db(root), root=root)


def _exit_with_report_error(service: ReportService, error: RunReportError) -> None:
    _print(service.failure(error))
    if typer is not None:
        raise typer.Exit(code=1) from error
    raise SystemExit(1) from error


def init_project(path: str = ".") -> None:
    root = _root(path)
    root.mkdir(parents=True, exist_ok=True)
    config = discover_config(root)
    config_path = write_config(root, config)
    (root / CODUCTOR_DIR / "runs").mkdir(parents=True, exist_ok=True)
    Database(root / CODUCTOR_DIR / "coductor.sqlite3")
    _print(f"已生成配置: {config_path}")


def run_goal(
    goal: str,
    mode: str = "auto",
    dry_run: bool = False,
    backend: str | None = None,
) -> None:
    root = _root(".")
    config = load_config(root)
    if backend:
        config.backend.provider = backend
    if dry_run:
        result = RunService(root, config, progress=_print_progress).dry_run(
            goal,
            mode=ExecutionMode(mode),
        )
        _print("dry-run: 已生成前置计划，不会启动 Worker。")
        _print(f"Run ID: {result.run_id}")
        _print(f"状态: {result.status}")
        _print(f"计划产物: {Path(result.run_dir) / '03_execution_plan.yaml'}")
        _print(f"下一步: coductor artifacts {result.run_id}")
        _print(f"继续执行: coductor resume {result.run_id}")
        return
    result = RunService(root, config, progress=_print_progress).run(
        goal,
        mode=ExecutionMode(mode),
    )
    _print(f"Run ID: {result.run_id}")
    _print(f"状态: {result.status}")
    _print(f"证据目录: {result.run_dir}")
    summary = _completion_summary(root, Path(result.run_dir), result.run_id)
    if summary:
        _print(summary)


def _print_progress(stage: str, message: str) -> None:
    _print(f"[{stage}] {message}")


def _completion_summary(root: Path, run_dir: Path, run_id: str) -> str:
    files = _generated_project_files(root)
    lines = [
        "",
        "下一步:",
        f"- 查看报告: coductor report {run_id}",
        f"- 查看产物: coductor artifacts {run_id}",
    ]
    if files:
        lines.append("- 生成文件:")
        lines.extend(f"  - {path}" for path in files[:12])
        if len(files) > 12:
            lines.append(f"  - ... 还有 {len(files) - 12} 个文件")
    preview = _static_preview_command(root)
    if preview:
        lines.extend(
            [
                "- 启动预览:",
                f"  {preview}",
                "  然后打开: http://127.0.0.1:4173",
                "  注意: ES module 页面不要直接用 file:// 打开。",
            ]
        )
    if (run_dir / "delivery-report.md").exists():
        lines.append(f"- 交付报告: {run_dir / 'delivery-report.md'}")
    return "\n".join(lines)


def _generated_project_files(root: Path) -> list[str]:
    ignored = {".coductor", ".git", "node_modules", ".venv", "vendor"}
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in ignored:
            continue
        files.append(relative.as_posix())
    return files


def _static_preview_command(root: Path) -> str | None:
    if (root / "src" / "index.html").exists():
        return "python3 -m http.server 4173 --bind 127.0.0.1 --directory src"
    if (root / "index.html").exists():
        return "python3 -m http.server 4173 --bind 127.0.0.1"
    return None


def status_run(
    run_id: str | None = None,
    watch: bool = False,
    json_output: bool = False,
    watch_count: int | None = None,
    watch_interval_seconds: float = 2.0,
) -> None:
    if watch:
        count = 0
        while True:
            _render_status_once(run_id, json_output)
            count += 1
            if watch_count is not None and count >= watch_count:
                return
            time.sleep(watch_interval_seconds)
    else:
        _render_status_once(run_id, json_output)


def _render_status_once(
    run_id: str | None = None,
    json_output: bool = False,
) -> None:
    root = _root(".")
    db = _db(root)
    row = db.get_run(run_id) if run_id else db.latest_run()
    if row is None:
        _print("未找到运行记录。")
        return
    if json_output:
        payload: dict[str, Any] = {"run": row, "checkpoint": None}
        checkpoint = db.get_checkpoint(row["run_id"])
        if checkpoint is not None:
            payload["checkpoint"] = {
                "current_stage": checkpoint.get("current_stage"),
                "completed_task_ids": checkpoint.get("completed_task_ids", []),
                "last_error": checkpoint.get("last_error"),
                "stale_artifacts": checkpoint.get("stale_artifacts", []),
            }
        _print_plain(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if Table is not None and console is not None:
        table = Table(title="Coductor Run Status")
        table.add_column("Run ID")
        table.add_column("Status")
        table.add_column("Run Dir")
        table.add_column("Updated")
        table.add_row(row["run_id"], row["status"], row["run_dir"], row["updated_at"])
        console.print(table)
    else:
        _print(json.dumps(row, ensure_ascii=False, indent=2))


def show_run(run_id: str) -> None:
    root = _root(".")
    service = _report_service(root)
    try:
        row = service.run_context(run_id, "show")
    except RunReportError as error:
        _exit_with_report_error(service, error)
    run_dir = Path(row["run_dir"])
    files = sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*.yaml"))
    _print(dump_yaml({"run": row, "artifacts": files}))


def resume_run(run_id: str) -> None:
    root = _root(".")
    service = _report_service(root)
    row = service.database.get_run(run_id)
    if row is None:
        _print(f"未找到 Run: {run_id}")
        return
    config = load_config(root)
    result = RunService(root, config).resume(run_id)
    resume_error = _resume_error_message(result.message)
    if result.status == RunStatus.HUMAN_REQUIRED and resume_error is not None:
        _exit_with_report_error(
            service,
            RunReportError(
                run_id=run_id,
                stage="resume",
                recoverable=True,
                next_command=f"coductor status {run_id}",
                message=resume_error,
            ),
        )
    _print(f"恢复完成: {result.run_id} -> {result.status}")


def _resume_error_message(message: str) -> str | None:
    operational_errors = (
        "already locked by another operation",
        "outside project runs directory",
        "unknown run",
    )
    return message if any(error in message for error in operational_errors) else None


def report_run(run_id: str) -> None:
    root = _root(".")
    service = _report_service(root)
    try:
        row = service.run_context(run_id, "report")
    except RunReportError as error:
        _exit_with_report_error(service, error)
    report = Path(row["run_dir"]) / "delivery-report.md"
    if not report.exists():
        _print(f"报告不存在: {report}")
        return
    _print(report.read_text(encoding="utf-8"))


def artifacts_run(run_id: str) -> None:
    root = _root(".")
    service = _report_service(root)
    try:
        _print(service.artifacts(run_id))
    except RunReportError as error:
        _exit_with_report_error(service, error)


def logs_run(
    run_id: str,
    stage: str | None = None,
    tail: int | None = None,
    json_output: bool = False,
) -> None:
    root = _root(".")
    service = _report_service(root)
    try:
        if json_output:
            payload = {
                "run_id": run_id,
                "events": service.log_events(run_id, stage_filter=stage, tail=tail),
            }
            _print_plain(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        _print(service.logs(run_id, stage_filter=stage, tail=tail))
    except RunReportError as error:
        _exit_with_report_error(service, error)


def explain_run(run_id: str) -> None:
    root = _root(".")
    service = _report_service(root)
    try:
        _print(service.explain(run_id))
    except RunReportError as error:
        _exit_with_report_error(service, error)


def control_run(run_id: str, command: str) -> None:
    root = _root(".")
    db = _db(root)
    service = ReportService(db, root=root)
    try:
        service.run_context(run_id, command)
    except RunReportError as error:
        _exit_with_report_error(service, error)
    owner = f"control:{command}:{os.getpid()}"
    if not db.acquire_run_lock(
        run_id,
        owner,
        now=_utc_now(),
        stale_after_seconds=RUN_LOCK_STALE_AFTER_SECONDS,
    ):
        _exit_with_report_error(
            service,
            RunReportError(
                run_id=run_id,
                stage=command,
                recoverable=True,
                next_command=f"coductor status {run_id}",
                message=f"run {run_id} is already locked by another operation",
            ),
        )
    try:
        try:
            row = service.validate_control_command(run_id, command)
        except RunReportError as error:
            _exit_with_report_error(service, error)
        if command == "verify":
            _rerun_verification(root, db, run_id, row)
            try:
                _print(service.control_result(run_id, command))
            except RunReportError as error:
                _exit_with_report_error(service, error)
            return
        if command == "review":
            _rerun_review(root, db, run_id, row)
            try:
                _print(service.control_result(run_id, command))
            except RunReportError as error:
                _exit_with_report_error(service, error)
            return
        if command == "approve":
            _approve_run(root, db, run_id, row)
            try:
                _print(service.control_result(run_id, command))
            except RunReportError as error:
                _exit_with_report_error(service, error)
            return
        status = CONTROL_STATUS[command]
        now = _utc_now()
        db.update_run_status(run_id, status, now)
        db.add_event(run_id, command, f"{command} requested by cli", now)
        _print(service.control_result(run_id, command))
    finally:
        db.release_run_lock(run_id, owner)


def approve_run(run_id: str) -> None:
    control_run(run_id, "approve")


def pause_run(run_id: str) -> None:
    control_run(run_id, "pause")


def stop_run(run_id: str) -> None:
    control_run(run_id, "stop")


def verify_run(run_id: str) -> None:
    control_run(run_id, "verify")


def review_run(run_id: str) -> None:
    control_run(run_id, "review")


def release_run(run_id: str) -> None:
    root = _root(".")
    db = _db(root)
    service = ReportService(db, root=root)
    try:
        row = service.run_context(run_id, "release")
    except RunReportError as error:
        _exit_with_report_error(service, error)
    if row["status"] != RunStatus.READY_FOR_HUMAN_REVIEW:
        _exit_with_report_error(
            service,
            RunReportError(
                run_id=run_id,
                stage="release",
                recoverable=True,
                next_command=f"coductor status {run_id}",
                message=f"cannot release run in status {row['status']}",
            ),
        )
    owner = f"control:release:{os.getpid()}"
    if not db.acquire_run_lock(
        run_id,
        owner,
        now=_utc_now(),
        stale_after_seconds=RUN_LOCK_STALE_AFTER_SECONDS,
    ):
        _exit_with_report_error(
            service,
            RunReportError(
                run_id=run_id,
                stage="release",
                recoverable=True,
                next_command=f"coductor status {run_id}",
                message=f"run {run_id} is already locked by another operation",
            ),
        )
    try:
        config = load_config(root)
        repo = ArtifactRepository(Path(row["run_dir"]))
        manifest = ReleaseService(
            root,
            db,
            WorkflowArtifactWriter(root, config),
        ).create_manifest(repo, run_id)
        _print(
            "\n".join(
                [
                    f"Run ID: {run_id}",
                    "Stage: release",
                    "Recoverable: yes",
                    f"Next command: coductor report {run_id}",
                    "",
                    f"Manifest: {repo.root / '08_release_manifest.yaml'}",
                    f"Status: {manifest.data.status}",
                    f"Ready: {'yes' if manifest.data.safety.ready else 'no'}",
                    "Remote actions: disabled",
                ]
            )
            + "\n"
        )
    finally:
        db.release_run_lock(run_id, owner)


def serve_web_console(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    allow_lan: bool = False,
) -> None:
    try:
        serve_console(
            _root("."),
            host=host,
            port=port,
            open_browser=open_browser,
            allow_lan=allow_lan,
        )
    except ServeOptionsError as error:
        _print(str(error))
        if typer is not None:
            raise typer.Exit(code=1) from error
        raise SystemExit(1) from error


def _approve_run(
    root: Path,
    db: Database,
    run_id: str,
    row: dict[str, str] | None = None,
) -> None:
    row = row or db.get_run(run_id)
    if row is None:
        return
    repo = ArtifactRepository(Path(row["run_dir"]))
    if _approve_spec_if_required(root, db, repo, run_id, row["run_dir"]):
        return
    plan_path = repo.root / "03_execution_plan.yaml"
    now = _utc_now()
    if not plan_path.exists():
        db.update_run_status(run_id, CONTROL_STATUS["approve"], now)
        db.add_event(run_id, "approve", "approve requested by cli", now)
        return
    plan = ArtifactEnvelope[ExecutionPlanData].model_validate(
        repo.read("03_execution_plan.yaml", ArtifactType.EXECUTION_PLAN).model_dump(mode="json")
    )
    if not plan.data.approval.required:
        db.update_run_status(run_id, CONTROL_STATUS["approve"], now)
        db.add_event(run_id, "approve", "approve requested by cli", now)
        return
    plan.data.approval.approved_by = "cli"
    repo.write_next_revision("03_execution_plan.yaml", plan)
    db.update_run_status(run_id, RunStatus.RUNNING, now)
    db.add_event(run_id, "approve", "parallel plan approved by cli", now)
    state = _approval_resume_state(db, root, run_id, row["run_dir"])
    WorkflowCheckpointStore(db, root / CODUCTOR_DIR / "runs").save(state, now)
    LangGraphCheckpointStore(db.path).save(state)


def _approve_spec_if_required(
    root: Path,
    db: Database,
    repo: ArtifactRepository,
    run_id: str,
    run_dir: str,
) -> bool:
    spec_path = repo.root / "02_spec.yaml"
    if not spec_path.exists():
        return False
    spec = ArtifactEnvelope[SpecificationData].model_validate(
        repo.read("02_spec.yaml", ArtifactType.SPECIFICATION).model_dump(mode="json")
    )
    if not spec.data.approval.required or spec.data.approval.approved_by:
        return False
    spec.data.approval.approved_by = "cli"
    repo.write_next_revision("02_spec.yaml", spec)
    now = _utc_now()
    db.update_run_status(run_id, RunStatus.RUNNING, now)
    db.add_event(run_id, "approve", "spec approved by cli", now)
    state = _spec_approval_resume_state(db, root, run_id, run_dir)
    WorkflowCheckpointStore(db, root / CODUCTOR_DIR / "runs").save(state, now)
    LangGraphCheckpointStore(db.path).save(state)
    return True


def _spec_approval_resume_state(
    db: Database,
    root: Path,
    run_id: str,
    run_dir: str,
) -> WorkflowState:
    current = LangGraphCheckpointStore(db.path).load(run_id)
    if current is None:
        current = WorkflowCheckpointStore(db, root / CODUCTOR_DIR / "runs").load(run_id)
    state = current or WorkflowState(run_id=run_id)
    state.status = RunStatus.RUNNING
    state.current_stage = "create_execution_plan"
    state.last_error = None
    state.run_dir = run_dir
    state.artifacts["02_spec"] = "02_spec.yaml"
    return state


def _approval_resume_state(
    db: Database,
    root: Path,
    run_id: str,
    run_dir: str,
) -> WorkflowState:
    current = LangGraphCheckpointStore(db.path).load(run_id)
    if current is None:
        current = WorkflowCheckpointStore(db, root / CODUCTOR_DIR / "runs").load(run_id)
    state = current or WorkflowState(run_id=run_id)
    state.status = RunStatus.RUNNING
    state.current_stage = "validate_execution_plan"
    state.last_error = None
    state.run_dir = run_dir
    state.artifacts["03_execution_plan"] = "03_execution_plan.yaml"
    return state


def _rerun_verification(
    root: Path,
    db: Database,
    run_id: str,
    row: dict[str, str] | None = None,
) -> None:
    row = row or db.get_run(run_id)
    if row is None:
        return
    config = load_config(root)
    repo = ArtifactRepository(Path(row["run_dir"]))
    writer = WorkflowArtifactWriter(root, config)
    gate_report = WorkflowVerificationService(root, config, writer).run_gates(repo, run_id)
    status = (
        RunStatus.READY_FOR_HUMAN_REVIEW
        if gate_report.data.required_gates_passed
        else RunStatus.HUMAN_REQUIRED
    )
    now = _utc_now()
    db.update_run_status(run_id, status, now)
    db.add_event(run_id, "verify", "quality gates rerun by cli", now)


def _rerun_review(
    root: Path,
    db: Database,
    run_id: str,
    row: dict[str, str] | None = None,
) -> None:
    row = row or db.get_run(run_id)
    if row is None:
        return
    config = load_config(root)
    repo = ArtifactRepository(Path(row["run_dir"]))
    writer = WorkflowArtifactWriter(root, config)
    delivery = ReviewDeliveryService(root, config, create_backend(config), writer)
    goal = ArtifactEnvelope[GoalData].model_validate(
        repo.read("00_goal.yaml", ArtifactType.GOAL).model_dump(mode="json")
    )
    gate_report = ArtifactEnvelope[GateReportData].model_validate(
        repo.read("05_gate_report.yaml", ArtifactType.GATE_REPORT).model_dump(mode="json")
    )
    strategy = _execution_strategy_for_review(repo)
    completed_task_ids = _completed_task_ids_for_review(repo)
    review = delivery.review(repo, run_id, gate_report, completed_task_ids)
    evidence = delivery.evidence(
        repo,
        run_id,
        goal,
        gate_report,
        review,
        strategy,
        completed_task_ids,
    )
    status = (
        RunStatus.READY_FOR_HUMAN_REVIEW
        if evidence.data.final_status == "ready_for_human_review"
        else RunStatus.HUMAN_REQUIRED
    )
    now = _utc_now()
    db.update_run_status(run_id, status, now)
    db.add_event(run_id, "review", "independent review rerun by cli", now)


def _execution_strategy_for_review(repo: ArtifactRepository) -> ExecutionStrategy:
    plan_path = repo.root / "03_execution_plan.yaml"
    if not plan_path.exists():
        return ExecutionStrategy.SOLO
    plan = ArtifactEnvelope[ExecutionPlanData].model_validate(
        repo.read("03_execution_plan.yaml", ArtifactType.EXECUTION_PLAN).model_dump(
            mode="json"
        )
    )
    return ExecutionStrategy(plan.data.strategy)


def _completed_task_ids_for_review(repo: ArtifactRepository) -> list[str]:
    task_ids: list[str] = []
    tasks_dir = repo.root / "tasks"
    if not tasks_dir.exists():
        return task_ids
    for path in sorted(tasks_dir.iterdir()):
        if path.is_dir() and (path / "patch.diff").exists():
            task_ids.append(path.name)
    return task_ids


def doctor() -> None:
    root = _root(".")
    config_path = root / "coductor.yaml"
    config = load_config(root) if config_path.exists() else discover_config(root)
    codex_bin = resolve_codex_bin()
    sdk_available = is_codex_sdk_available()
    effective_provider = effective_backend_provider(
        config.backend.provider,
        fallback=config.backend.fallback,
        sdk_available=sdk_available,
    )
    capability = describe_backend_capability(
        effective_provider,
        sdk_available=sdk_available,
    )
    checks = {
        "coductor_version": VERSION,
        "python": sys.version.split()[0],
        "git": shutil.which("git") or "missing",
        "codex": shutil.which("codex") or "missing",
        "config": "present" if config_path.exists() else "missing",
        "database": (
            "present"
            if (root / CODUCTOR_DIR / "coductor.sqlite3").exists()
            else "not initialized"
        ),
        "backend_provider": config.backend.provider,
        "backend_effective_provider": effective_provider,
        "backend_fallback": config.backend.fallback,
        "codex_exec_bin": codex_bin,
        "codex_sdk_available": sdk_available,
        "backend_available": capability.available,
        "backend_resume_thread": capability.supports_resume_thread,
        "backend_streaming_logs": capability.supports_streaming_logs,
        "backend_cancel": capability.supports_cancel,
        "backend_usage": capability.supports_usage,
        "network_default": "disabled",
        "dangerous_defaults": "git_push=false, pull_request=false",
    }
    _print(dump_yaml(checks))


if typer is not None:

    def version_callback(value: bool) -> None:
        if value:
            _print(f"coductor {VERSION}")
            raise typer.Exit

    @app.callback()  # type: ignore[untyped-decorator]
    def main_callback(
        ctx: typer.Context,
        version: Annotated[
            bool,
            typer.Option(
                "--version",
                callback=version_callback,
                is_eager=True,
                help="显示版本并退出 / Show version and exit.",
            ),
        ] = False,
    ) -> None:
        del version
        if ctx.invoked_subcommand is None:
            print_quick_start()
            raise typer.Exit

    @app.command("init", help="初始化当前项目 / Initialize a project.")  # type: ignore[untyped-decorator]
    def init_command(
        path: Annotated[str, typer.Argument(help="被管理仓库路径 / Managed repo path")] = ".",
    ) -> None:
        init_project(path)

    @app.command("run", help="运行研发目标 / Run a coding goal.")  # type: ignore[untyped-decorator]
    def run_command(
        goal: Annotated[str, typer.Argument(help="自然语言研发目标 / Natural-language goal")],
        mode: Annotated[
            str,
            typer.Option("--mode", help="执行模式 / Execution mode: auto|solo|pipeline|parallel"),
        ] = "auto",
        dry_run: Annotated[
            bool,
            typer.Option("--dry-run", help="只生成前置计划 / Plan only, do not start workers"),
        ] = False,
        backend: Annotated[
            str | None,
            typer.Option("--backend", help="后端 / Backend: fake|codex_sdk|codex_exec"),
        ] = None,
    ) -> None:
        try:
            run_goal(goal, mode, dry_run, backend)
        except CoductorError as error:
            _print(error.to_display())
            raise typer.Exit(code=1) from error

    @app.command("status", help="查看运行状态 / Show run status.")  # type: ignore[untyped-decorator]
    def status_command(
        run_id: Annotated[str | None, typer.Argument(help="Run ID，可省略为最新运行")] = None,
        watch: Annotated[bool, typer.Option("--watch", help="持续刷新 / Watch updates")] = False,
        watch_count: Annotated[
            int | None,
            typer.Option(
                "--watch-count",
                help="最多刷新次数 / Maximum refresh count",
            ),
        ] = None,
        json_output: Annotated[
            bool,
            typer.Option("--json", help="输出机器可读 JSON / Output machine-readable JSON"),
        ] = False,
    ) -> None:
        status_run(run_id, watch, json_output, watch_count=watch_count)

    @app.command("show", help="显示运行摘要 / Show run summary.")  # type: ignore[untyped-decorator]
    def show_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        show_run(run_id)

    @app.command("resume", help="恢复运行 / Resume a run.")  # type: ignore[untyped-decorator]
    def resume_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        resume_run(run_id)

    @app.command("report", help="查看交付报告 / Show delivery report.")  # type: ignore[untyped-decorator]
    def report_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        report_run(run_id)

    @app.command("artifacts", help="查看产物列表 / List run artifacts.")  # type: ignore[untyped-decorator]
    def artifacts_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        artifacts_run(run_id)

    @app.command("logs", help="查看事件日志 / Show run event logs.")  # type: ignore[untyped-decorator]
    def logs_command(
        run_id: Annotated[str, typer.Argument(help="Run ID")],
        stage: Annotated[
            str | None,
            typer.Option("--stage", help="按阶段过滤 / Filter by stage"),
        ] = None,
        tail: Annotated[
            int | None,
            typer.Option("--tail", help="只显示最近 N 条 / Show only the last N events"),
        ] = None,
        json_output: Annotated[
            bool,
            typer.Option("--json", help="输出机器可读 JSON / Output machine-readable JSON"),
        ] = False,
    ) -> None:
        logs_run(run_id, stage, tail, json_output)

    @app.command("explain", help="解释状态和下一步 / Explain state and next command.")  # type: ignore[untyped-decorator]
    def explain_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        explain_run(run_id)

    @app.command("approve", help="人工批准运行 / Mark a run approved.")  # type: ignore[untyped-decorator]
    def approve_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        approve_run(run_id)

    @app.command("pause", help="暂停运行 / Mark a run paused.")  # type: ignore[untyped-decorator]
    def pause_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        pause_run(run_id)

    @app.command("stop", help="停止运行 / Mark a run stopped.")  # type: ignore[untyped-decorator]
    def stop_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        stop_run(run_id)

    @app.command("verify", help="请求重新验证 / Request verification.")  # type: ignore[untyped-decorator]
    def verify_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        verify_run(run_id)

    @app.command("review", help="请求人工审查 / Request review.")  # type: ignore[untyped-decorator]
    def review_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        review_run(run_id)

    @app.command("release", help="生成发布清单 / Generate release manifest.")  # type: ignore[untyped-decorator]
    def release_command(run_id: Annotated[str, typer.Argument(help="Run ID")]) -> None:
        release_run(run_id)

    @app.command("serve", help="启动本地 Web 控制台 / Start local Web console.")  # type: ignore[untyped-decorator]
    def serve_command(
        host: Annotated[
            str,
            typer.Option("--host", help="监听地址 / Host to bind."),
        ] = "127.0.0.1",
        port: Annotated[
            int,
            typer.Option("--port", help="监听端口 / Port to bind."),
        ] = 8765,
        open_browser: Annotated[
            bool,
            typer.Option("--open", help="启动后打开浏览器 / Open browser after start."),
        ] = False,
        allow_lan: Annotated[
            bool,
            typer.Option("--allow-lan", help="允许非 loopback 监听 / Allow LAN binding."),
        ] = False,
    ) -> None:
        serve_web_console(
            host=host,
            port=port,
            open_browser=open_browser,
            allow_lan=allow_lan,
        )

    @app.command("doctor", help="检查安装与安全默认值 / Check installation and defaults.")  # type: ignore[untyped-decorator]
    def doctor_command() -> None:
        doctor()


def _argparse_main(argv: list[str] | None = None) -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(prog="coductor")
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init")
    init_parser.add_argument("path", nargs="?", default=".")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("goal")
    run_parser.add_argument("--mode", default="auto")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--backend")
    status_parser = sub.add_parser("status")
    status_parser.add_argument("run_id", nargs="?")
    status_parser.add_argument("--watch", action="store_true")
    status_parser.add_argument("--watch-count", type=int)
    status_parser.add_argument("--json", action="store_true")
    show_parser = sub.add_parser("show")
    show_parser.add_argument("run_id")
    resume_parser = sub.add_parser("resume")
    resume_parser.add_argument("run_id")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("run_id")
    artifacts_parser = sub.add_parser("artifacts")
    artifacts_parser.add_argument("run_id")
    logs_parser = sub.add_parser("logs")
    logs_parser.add_argument("run_id")
    logs_parser.add_argument("--stage")
    logs_parser.add_argument("--tail", type=int)
    logs_parser.add_argument("--json", action="store_true")
    explain_parser = sub.add_parser("explain")
    explain_parser.add_argument("run_id")
    for command in ["approve", "pause", "stop", "verify", "review"]:
        parser = sub.add_parser(command)
        parser.add_argument("run_id")
    release_parser = sub.add_parser("release")
    release_parser.add_argument("run_id")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true")
    serve_parser.add_argument("--allow-lan", action="store_true")
    sub.add_parser("doctor")
    args = parser.parse_args(argv)
    if args.command == "init":
        init_project(args.path)
    elif args.command == "run":
        run_goal(args.goal, args.mode, args.dry_run, args.backend)
    elif args.command == "status":
        status_run(args.run_id, args.watch, args.json, watch_count=args.watch_count)
    elif args.command == "show":
        show_run(args.run_id)
    elif args.command == "resume":
        resume_run(args.run_id)
    elif args.command == "report":
        report_run(args.run_id)
    elif args.command == "artifacts":
        artifacts_run(args.run_id)
    elif args.command == "logs":
        logs_run(args.run_id, args.stage, args.tail, args.json)
    elif args.command == "explain":
        explain_run(args.run_id)
    elif args.command in {"approve", "pause", "stop", "verify", "review"}:
        control_run(args.run_id, args.command)
    elif args.command == "release":
        release_run(args.run_id)
    elif args.command == "serve":
        serve_web_console(args.host, args.port, args.open, args.allow_lan)
    elif args.command == "doctor":
        doctor()


def main() -> None:
    if typer is None:
        _argparse_main()
    else:
        app()


if __name__ == "__main__":
    main()
