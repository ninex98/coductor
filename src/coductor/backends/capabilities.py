"""Backend capability registry for diagnostics and orchestration decisions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BackendCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    available: bool
    supports_resume_thread: bool
    supports_streaming_logs: bool
    supports_cancel: bool
    supports_usage: bool
    supports_read_only: bool
    supports_workspace_write: bool
    supports_network_access: bool
    notes: list[str] = []


def describe_backend_capability(
    provider: str,
    *,
    sdk_available: bool,
) -> BackendCapability:
    if provider == "fake":
        return BackendCapability(
            provider=provider,
            available=True,
            supports_resume_thread=True,
            supports_streaming_logs=False,
            supports_cancel=True,
            supports_usage=False,
            supports_read_only=True,
            supports_workspace_write=True,
            supports_network_access=False,
            notes=["offline deterministic backend for tests and demos"],
        )
    if provider == "codex_exec":
        return BackendCapability(
            provider=provider,
            available=True,
            supports_resume_thread=False,
            supports_streaming_logs=False,
            supports_cancel=False,
            supports_usage=False,
            supports_read_only=True,
            supports_workspace_write=True,
            supports_network_access=False,
            notes=["uses codex exec via stdin and Coductor-owned YAML artifacts"],
        )
    if provider == "codex_sdk":
        return BackendCapability(
            provider=provider,
            available=sdk_available,
            supports_resume_thread=sdk_available,
            supports_streaming_logs=sdk_available,
            supports_cancel=sdk_available,
            supports_usage=sdk_available,
            supports_read_only=sdk_available,
            supports_workspace_write=sdk_available,
            supports_network_access=False,
            notes=(
                ["SDK import available"]
                if sdk_available
                else ["SDK unavailable; configure fallback=codex_exec"]
            ),
        )
    return BackendCapability(
        provider=provider,
        available=False,
        supports_resume_thread=False,
        supports_streaming_logs=False,
        supports_cancel=False,
        supports_usage=False,
        supports_read_only=False,
        supports_workspace_write=False,
        supports_network_access=False,
        notes=["unknown backend provider"],
    )


def effective_backend_provider(
    provider: str,
    *,
    fallback: str,
    sdk_available: bool,
) -> str:
    if provider == "codex_sdk" and not sdk_available and fallback == "codex_exec":
        return "codex_exec"
    return provider
