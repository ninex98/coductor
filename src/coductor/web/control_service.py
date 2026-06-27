"""Safe run actions for the local web console."""

from __future__ import annotations

import os
import time
from pathlib import Path

from coductor.artifacts.repository import ArtifactRepository
from coductor.config.loader import load_config
from coductor.constants import CODUCTOR_DIR
from coductor.domain.enums import RunStatus
from coductor.exceptions import CoductorError
from coductor.services.release_service import ReleaseService
from coductor.services.report_service import CONTROL_STATUS, ReportService, RunReportError
from coductor.services.run_service import RUN_LOCK_STALE_AFTER_SECONDS, RunService, utc_now
from coductor.storage.database import Database
from coductor.web.schemas import ConsoleActionResult
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class ConsoleControlError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        recoverable: bool = True,
        next_command: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.recoverable = recoverable
        self.next_command = next_command


class ConsoleControlService:
    DEFAULT_ACTION_WINDOW_SECONDS = 2.0

    def __init__(self, root: Path) -> None:
        self.root = root
        self.db = Database(root / CODUCTOR_DIR / "coductor.sqlite3")
        self.report = ReportService(self.db, root=root)
        self._recent_actions: dict[tuple[str, str], float] = {}

    def run_action(self, run_id: str, action: str) -> ConsoleActionResult:
        self._check_action_window(run_id, action)
        if action == "resume":
            return self._resume(run_id)
        if action == "release":
            return self._release(run_id)
        if action in {"approve", "pause", "stop", "verify", "review"}:
            return self._control(run_id, action)
        raise ConsoleControlError(
            f"unsupported action: {action}",
            next_command=f"coductor status {run_id}",
        )

    def _check_action_window(self, run_id: str, action: str) -> None:
        now = time.monotonic()
        key = (run_id, action)
        last_seen = self._recent_actions.get(key)
        if (
            last_seen is not None
            and now - last_seen < self.DEFAULT_ACTION_WINDOW_SECONDS
        ):
            raise ConsoleControlError(
                f"too many repeated {action} requests for {run_id}",
                status_code=429,
                next_command=f"coductor status {run_id}",
            )
        self._recent_actions[key] = now

    def _control(self, run_id: str, action: str) -> ConsoleActionResult:
        self._run_context(run_id, action)
        owner = self._acquire(run_id, action)
        try:
            try:
                self.report.validate_control_command(run_id, action)
            except RunReportError as error:
                raise _control_error_from_report(error) from error
            if action in {"verify", "review", "approve"}:
                try:
                    self._run_cli_control_helper(run_id, action)
                except CoductorError as error:
                    raise _control_error_from_coductor(error, run_id) from error
                row = self.report.run_context(run_id, action)
                return ConsoleActionResult(
                    run_id=run_id,
                    action=action,
                    status=row["status"],
                    message=f"{action} completed by web",
                    next_command=f"coductor status {run_id}",
                )
            status = CONTROL_STATUS[action]
            now = utc_now()
            self.db.update_run_status(run_id, status, now)
            self.db.add_event(run_id, action, f"{action} requested by web", now)
            return ConsoleActionResult(
                run_id=run_id,
                action=action,
                status=status,
                message=f"{action} requested by web",
                next_command=f"coductor status {run_id}",
            )
        finally:
            self.db.release_run_lock(run_id, owner)

    def _release(self, run_id: str) -> ConsoleActionResult:
        row = self._run_context(run_id, "release")
        if row["status"] != RunStatus.READY_FOR_HUMAN_REVIEW:
            raise ConsoleControlError(
                f"cannot release run in status {row['status']}",
                next_command=f"coductor status {run_id}",
            )
        owner = self._acquire(run_id, "release")
        try:
            config = load_config(self.root)
            repo = ArtifactRepository(Path(row["run_dir"]))
            try:
                ReleaseService(
                    self.root,
                    self.db,
                    WorkflowArtifactWriter(self.root, config),
                ).create_manifest(repo, run_id)
            except CoductorError as error:
                raise _control_error_from_coductor(error, run_id) from error
            return ConsoleActionResult(
                run_id=run_id,
                action="release",
                status=row["status"],
                message="release manifest generated by web",
                next_command=f"coductor report {run_id}",
            )
        finally:
            self.db.release_run_lock(run_id, owner)

    def _resume(self, run_id: str) -> ConsoleActionResult:
        try:
            result = RunService(self.root, load_config(self.root)).resume(run_id)
        except CoductorError as error:
            raise _control_error_from_coductor(error, run_id) from error
        return ConsoleActionResult(
            run_id=run_id,
            action="resume",
            status=str(result.status),
            message=result.message or "resume requested by web",
            next_command=f"coductor status {run_id}",
        )

    def _run_context(self, run_id: str, action: str) -> dict[str, str]:
        try:
            return self.report.run_context(run_id, action)
        except RunReportError as error:
            raise _control_error_from_report(error) from error

    def _acquire(self, run_id: str, action: str) -> str:
        owner = f"web:{action}:{os.getpid()}"
        if self.db.acquire_run_lock(
            run_id,
            owner,
            now=utc_now(),
            stale_after_seconds=RUN_LOCK_STALE_AFTER_SECONDS,
        ):
            return owner
        raise ConsoleControlError(
            f"run {run_id} is already locked by another operation",
            status_code=409,
            next_command=f"coductor status {run_id}",
        )

    def _run_cli_control_helper(self, run_id: str, action: str) -> None:
        from coductor import cli as cli_module

        if action == "approve":
            cli_module._approve_run(self.root, self.db, run_id)  # noqa: SLF001
            return
        if action == "verify":
            cli_module._rerun_verification(self.root, self.db, run_id)  # noqa: SLF001
            return
        if action == "review":
            cli_module._rerun_review(self.root, self.db, run_id)  # noqa: SLF001
            return
        raise ConsoleControlError(
            f"unsupported action: {action}",
            next_command=f"coductor status {run_id}",
        )


def _control_error_from_report(error: RunReportError) -> ConsoleControlError:
    return ConsoleControlError(
        error.message,
        recoverable=error.recoverable,
        next_command=error.next_command,
    )


def _control_error_from_coductor(error: CoductorError, run_id: str) -> ConsoleControlError:
    return ConsoleControlError(
        str(error),
        status_code=400,
        recoverable=error.recoverable,
        next_command=error.next_command or f"coductor status {run_id}",
    )
