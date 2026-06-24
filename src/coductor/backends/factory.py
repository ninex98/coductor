"""Backend selection and fallback policy."""

from __future__ import annotations

from importlib.util import find_spec

from coductor.backends.base import CodingBackend
from coductor.backends.codex_exec import CodexExecBackend
from coductor.backends.codex_sdk import CodexSdkBackend
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.exceptions import BackendUnavailableError


def create_backend(
    config: CoductorConfig,
    *,
    sdk_available: bool | None = None,
) -> CodingBackend:
    provider = config.backend.provider
    if provider == "fake":
        return FakeCodingBackend()
    if provider == "codex_exec":
        return CodexExecBackend()
    if provider == "codex_sdk":
        sdk_available = is_codex_sdk_available() if sdk_available is None else sdk_available
        if sdk_available is False and config.backend.fallback == "codex_exec":
            return CodexExecBackend()
        return CodexSdkBackend(config.backend)
    raise BackendUnavailableError(
        f"unknown backend provider: {provider}",
        stage="backend",
        recoverable=False,
        next_command="coductor doctor",
    )


def is_codex_sdk_available() -> bool:
    return find_spec("openai_codex") is not None
