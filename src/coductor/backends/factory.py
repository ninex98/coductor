"""Backend selection and fallback policy."""

from __future__ import annotations

import shutil
from importlib.util import find_spec
from pathlib import Path

from coductor.backends.base import CodingBackend
from coductor.backends.codex_exec import CodexExecBackend
from coductor.backends.codex_sdk import CodexSdkBackend
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.exceptions import BackendUnavailableError

CODEX_APP_CLI = Path("/Applications/Codex.app/Contents/Resources/codex")


def create_backend(
    config: CoductorConfig,
    *,
    sdk_available: bool | None = None,
) -> CodingBackend:
    provider = config.backend.provider
    if provider == "fake":
        return FakeCodingBackend()
    if provider == "codex_exec":
        return CodexExecBackend(codex_bin=resolve_codex_bin())
    if provider == "codex_sdk":
        sdk_available = is_codex_sdk_available() if sdk_available is None else sdk_available
        if sdk_available is False and config.backend.fallback == "codex_exec":
            return CodexExecBackend(codex_bin=resolve_codex_bin())
        return CodexSdkBackend(config.backend)
    raise BackendUnavailableError(
        f"unknown backend provider: {provider}",
        stage="backend",
        recoverable=False,
        next_command="coductor doctor",
    )


def is_codex_sdk_available() -> bool:
    return find_spec("openai_codex") is not None


def resolve_codex_bin() -> str:
    path_codex = shutil.which("codex")
    if path_codex:
        return path_codex
    if CODEX_APP_CLI.exists():
        return CODEX_APP_CLI.as_posix()
    return "codex"
