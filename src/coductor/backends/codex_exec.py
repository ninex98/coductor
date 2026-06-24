"""`codex exec` backend fallback."""

from __future__ import annotations

import subprocess
from pathlib import Path

from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.config.models import BackendConfig
from coductor.domain.enums import WorkerStatus
from coductor.domain.ids import new_id


class CodexExecBackend:
    def __init__(
        self,
        config: BackendConfig | None = None,
        *,
        codex_bin: str = "codex",
        schemas_dir: Path | str = "schemas",
        timeout_seconds: int = 1800,
    ) -> None:
        self.config = config
        self.codex_bin = codex_bin
        self.schemas_dir = Path(schemas_dir)
        self.timeout_seconds = timeout_seconds

    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        return WorkerHandle(worker_id=request.worker_id, thread_id=new_id("codexexec"))

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        schema_name = "review_report" if request.role == "reviewer" else "worker_result"
        command = self.build_command(
            prompt_path=None,
            sandbox=request.sandbox,
            output_schema=schema_name,
        )
        completed = subprocess.run(
            command,
            input=request.prompt,
            cwd=request.workspace_path,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary=completed.stdout.strip() or completed.stderr.strip(),
            commands_run=[" ".join(command)],
            exit_reason="completed" if completed.returncode == 0 else "failed",
        )

    def build_command(
        self,
        *,
        prompt_path: Path | str | None,
        sandbox: str,
        output_schema: Path | str,
    ) -> list[str]:
        del prompt_path
        sandbox_value = self._sandbox_value(sandbox)
        schema_path = self._schema_path(output_schema)
        return [
            self.codex_bin,
            "exec",
            "--sandbox",
            sandbox_value,
            "--output-schema",
            schema_path.as_posix(),
            "--json",
            "-",
        ]

    def _schema_path(self, output_schema: Path | str) -> Path:
        if isinstance(output_schema, Path):
            return output_schema
        if output_schema.endswith(".json"):
            return Path(output_schema)
        return self.schemas_dir / f"{output_schema}.schema.json"

    def _sandbox_value(self, sandbox: str) -> str:
        return sandbox.replace("_", "-")

    def cancel_worker(self, handle: WorkerHandle) -> None:
        return None

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.COMPLETED
