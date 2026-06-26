"""Coductor command line interface."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any

from coductor.artifacts.serializer import dump_yaml
from coductor.config.loader import discover_config, load_config, write_config
from coductor.constants import CODUCTOR_DIR, VERSION
from coductor.domain.enums import ExecutionMode
from coductor.exceptions import CoductorError
from coductor.services.report_service import CONTROL_STATUS, ReportService, RunReportError
from coductor.services.run_service import RunService
from coductor.storage.database import Database

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
CLI_HELP = """
Coductor / 确定性 AI Coding 工作流引擎

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

Common commands / 常用命令:
  init       初始化当前项目 / Initialize a project
  run        运行研发目标 / Run a coding goal
  status     查看运行状态 / Show run status
  artifacts  查看产物列表 / List run artifacts
  logs       查看事件日志 / Show run event logs
  explain    解释状态和下一步 / Explain state and next command
  report     查看交付报告 / Show delivery report
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
    _print(CLI_HELP.strip())


def _root(path: str | Path = ".") -> Path:
    return Path(path).resolve()


def _db(root: Path) -> Database:
    return Database(root / CODUCTOR_DIR / "coductor.sqlite3")


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _report_service(root: Path) -> ReportService:
    return ReportService(_db(root))


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
        _print("dry-run: 将执行 Goal → Inspect → Spec → Plan，但不会启动 Worker。")
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
) -> None:
    del watch
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
    row = _db(root).get_run(run_id)
    if row is None:
        _print(f"未找到 Run: {run_id}")
        return
    run_dir = Path(row["run_dir"])
    files = sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*.yaml"))
    _print(dump_yaml({"run": row, "artifacts": files}))


def resume_run(run_id: str) -> None:
    root = _root(".")
    row = _db(root).get_run(run_id)
    if row is None:
        _print(f"未找到 Run: {run_id}")
        return
    config = load_config(root)
    result = RunService(root, config).resume(run_id)
    _print(f"恢复完成: {result.run_id} -> {result.status}")


def report_run(run_id: str) -> None:
    root = _root(".")
    row = _db(root).get_run(run_id)
    if row is None:
        _print(f"未找到 Run: {run_id}")
        return
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
    service = ReportService(db)
    try:
        service.run_context(run_id, command)
    except RunReportError as error:
        _exit_with_report_error(service, error)
    status = CONTROL_STATUS[command]
    now = _utc_now()
    db.update_run_status(run_id, status, now)
    db.add_event(run_id, command, f"{command} requested by cli", now)
    _print(service.control_result(run_id, command))


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


def doctor() -> None:
    root = _root(".")
    config_path = root / "coductor.yaml"
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
        json_output: Annotated[
            bool,
            typer.Option("--json", help="输出机器可读 JSON / Output machine-readable JSON"),
        ] = False,
    ) -> None:
        status_run(run_id, watch, json_output)

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
    sub.add_parser("doctor")
    args = parser.parse_args(argv)
    if args.command == "init":
        init_project(args.path)
    elif args.command == "run":
        run_goal(args.goal, args.mode, args.dry_run, args.backend)
    elif args.command == "status":
        status_run(args.run_id, args.watch, args.json)
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
    elif args.command == "doctor":
        doctor()


def main() -> None:
    if typer is None:
        _argparse_main()
    else:
        app()


if __name__ == "__main__":
    main()
