"""`codex exec` backend fallback."""

from __future__ import annotations

import subprocess

from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.domain.enums import WorkerStatus
from coductor.domain.ids import new_id


class CodexExecBackend:
    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        return WorkerHandle(worker_id=request.worker_id, thread_id=new_id("codexexec"))

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        completed = subprocess.run(
            ["codex", "exec", request.prompt],
            cwd=request.workspace_path,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary=completed.stdout.strip() or completed.stderr.strip(),
            commands_run=["codex exec"],
            exit_reason="completed" if completed.returncode == 0 else "failed",
        )

    def cancel_worker(self, handle: WorkerHandle) -> None:
        return None

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.COMPLETED
