"""Codex SDK backend placeholder.

The SDK implementation is intentionally behind this interface. The MVP raises a
clear error when the SDK is not installed, allowing config fallback to `codex exec`.
"""

from __future__ import annotations

from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.config.models import BackendConfig
from coductor.domain.enums import WorkerStatus
from coductor.exceptions import BackendUnavailableError


class CodexSdkBackend:
    def __init__(self, config: BackendConfig | None = None) -> None:
        self.config = config

    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        raise BackendUnavailableError(
            "openai-codex Python SDK is not installed in this environment",
            stage="backend",
            recoverable=True,
            next_command="coductor run --backend codex_exec",
        )

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        raise BackendUnavailableError(
            "openai-codex Python SDK is not installed in this environment",
            stage="backend",
            recoverable=True,
            next_command="coductor run --backend codex_exec",
        )

    def cancel_worker(self, handle: WorkerHandle) -> None:
        return None

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.FAILED
