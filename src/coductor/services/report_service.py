"""Human-facing run reports for the CLI control plane."""

from __future__ import annotations

from pathlib import Path

from coductor.storage.database import Database
from coductor.workflow.state import WorkflowState

CONTROL_STATUS: dict[str, str] = {
    "approve": "approved",
    "pause": "paused",
    "stop": "stopped",
    "verify": "verification_requested",
    "review": "review_requested",
}

CONTROL_ALLOWED_STATUSES: dict[str, set[str]] = {
    "approve": {"human_required"},
    "pause": {"running"},
    "stop": {"running"},
}


class ReportService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def run_context(self, run_id: str, stage: str) -> dict[str, str]:
        row = self.database.get_run(run_id)
        if row is None:
            raise RunReportError(
                run_id=run_id,
                stage=stage,
                recoverable=True,
                next_command="coductor status",
                message="未找到运行记录。",
            )
        return row

    def artifacts(self, run_id: str) -> str:
        row = self.run_context(run_id, "artifacts")
        run_dir = Path(row["run_dir"])
        files = sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*.yaml"))
        lines = self._header(
            run_id=run_id,
            stage="artifacts",
            recoverable=True,
            next_command=f"coductor show {run_id}",
        )
        checkpoint = self._checkpoint(run_id)
        if checkpoint is not None:
            lines.extend(self._checkpoint_lines(checkpoint))
            lines.append("")
        lines.extend(files or ["No YAML artifacts found."])
        return "\n".join(lines) + "\n"

    def logs(
        self,
        run_id: str,
        *,
        stage_filter: str | None = None,
        tail: int | None = None,
    ) -> str:
        self.run_context(run_id, "logs")
        events = self.log_events(run_id, stage_filter=stage_filter, tail=tail)
        lines = self._header(
            run_id=run_id,
            stage="logs",
            recoverable=True,
            next_command=f"coductor explain {run_id}",
        )
        if events:
            lines.extend(
                f"{event['created_at']} {event['stage']}: {event['message']}"
                for event in events
            )
        else:
            lines.append("No events recorded.")
        return "\n".join(lines) + "\n"

    def log_events(
        self,
        run_id: str,
        *,
        stage_filter: str | None = None,
        tail: int | None = None,
    ) -> list[dict[str, str]]:
        self.run_context(run_id, "logs")
        events = self.database.list_events(run_id)
        if stage_filter is not None:
            events = [event for event in events if event["stage"] == stage_filter]
        if tail is not None and tail >= 0:
            events = events[-tail:] if tail else []
        return events

    def explain(self, run_id: str) -> str:
        row = self.run_context(run_id, "explain")
        next_command = self._next_command_for(row["status"], run_id)
        lines = self._header(
            run_id=run_id,
            stage="explain",
            recoverable=True,
            next_command=next_command,
        )
        lines.extend(
            [
                f"Status: {row['status']}",
                f"Run dir: {row['run_dir']}",
                f"Updated: {row['updated_at']}",
            ]
        )
        checkpoint = self._checkpoint(run_id)
        if checkpoint is not None:
            lines.extend(self._checkpoint_lines(checkpoint))
        return "\n".join(lines) + "\n"

    def control_result(self, run_id: str, command: str) -> str:
        row = self.run_context(run_id, command)
        next_command = self._next_command_for(row["status"], run_id)
        lines = self._header(
            run_id=run_id,
            stage=command,
            recoverable=True,
            next_command=next_command,
        )
        lines.append(f"Status: {row['status']}")
        return "\n".join(lines) + "\n"

    def validate_control_command(self, run_id: str, command: str) -> dict[str, str]:
        row = self.run_context(run_id, command)
        allowed = CONTROL_ALLOWED_STATUSES.get(command)
        if allowed is not None and row["status"] not in allowed:
            raise RunReportError(
                run_id=run_id,
                stage=command,
                recoverable=True,
                next_command=f"coductor status {run_id}",
                message=f"cannot {command} run in status {row['status']}",
            )
        return row

    def failure(self, error: RunReportError) -> str:
        lines = self._header(
            run_id=error.run_id,
            stage=error.stage,
            recoverable=error.recoverable,
            next_command=error.next_command,
        )
        lines.append(error.message)
        return "\n".join(lines) + "\n"

    def _header(
        self,
        *,
        run_id: str,
        stage: str,
        recoverable: bool,
        next_command: str,
    ) -> list[str]:
        return [
            f"Run ID: {run_id}",
            f"Stage: {stage}",
            f"Recoverable: {'yes' if recoverable else 'no'}",
            f"Next command: {next_command}",
            "",
        ]

    def _next_command_for(self, status: str, run_id: str) -> str:
        if status == "ready_for_human_review":
            return f"coductor report {run_id}"
        if status == "human_required":
            return f"coductor explain {run_id}"
        if status == "running":
            return f"coductor logs {run_id}"
        return f"coductor status {run_id}"

    def _checkpoint(self, run_id: str) -> WorkflowState | None:
        data = self.database.get_checkpoint(run_id)
        if data is None:
            return None
        return WorkflowState.model_validate(data)

    def _checkpoint_lines(self, state: WorkflowState) -> list[str]:
        lines = [
            f"Current stage: {state.current_stage}",
            f"Completed tasks: {', '.join(state.completed_task_ids) or '-'}",
        ]
        if state.last_error:
            lines.append(f"Last error: {state.last_error}")
        if state.stale_artifacts:
            lines.append("Stale artifacts:")
            lines.extend(f"- {artifact}" for artifact in state.stale_artifacts)
        return lines


class RunReportError(Exception):
    def __init__(
        self,
        *,
        run_id: str,
        stage: str,
        recoverable: bool,
        next_command: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.stage = stage
        self.recoverable = recoverable
        self.next_command = next_command
        self.message = message
