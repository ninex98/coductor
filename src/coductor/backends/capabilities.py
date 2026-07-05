"""Backend capability registry for diagnostics and orchestration decisions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BackendStability = Literal["stable", "test_only", "experimental", "unimplemented", "unknown"]
CODEX_SDK_BACKEND_IMPLEMENTED = False


class BackendCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    available: bool
    implemented: bool
    stability: BackendStability
    supports_resume_thread: bool
    supports_streaming_logs: bool
    supports_cancel: bool
    supports_usage: bool
    supports_read_only: bool
    supports_workspace_write: bool
    supports_network_access: bool
    notes: list[str] = Field(default_factory=list)


def describe_backend_capability(
    provider: str,
    *,
    sdk_available: bool,
) -> BackendCapability:
    if provider == "fake":
        return BackendCapability(
            provider=provider,
            available=True,
            implemented=True,
            stability="test_only",
            supports_resume_thread=True,
            supports_streaming_logs=False,
            supports_cancel=True,
            supports_usage=False,
            supports_read_only=True,
            supports_workspace_write=True,
            supports_network_access=False,
            notes=[
                "offline deterministic backend for tests and demos",
                "thread resume and cancel are simulated, not production Codex capabilities",
            ],
        )
    if provider == "codex_exec":
        return BackendCapability(
            provider=provider,
            available=True,
            implemented=True,
            stability="stable",
            supports_resume_thread=False,
            supports_streaming_logs=False,
            supports_cancel=False,
            supports_usage=False,
            supports_read_only=True,
            supports_workspace_write=True,
            supports_network_access=False,
            notes=[
                "uses codex exec via stdin and Coductor-owned YAML artifacts",
                (
                    "does not expose durable thread resume, streaming logs, cancel, "
                    "or real token usage"
                ),
            ],
        )
    if provider == "codex_sdk":
        implemented = CODEX_SDK_BACKEND_IMPLEMENTED and sdk_available
        return BackendCapability(
            provider=provider,
            available=sdk_available,
            implemented=implemented,
            stability="experimental" if implemented else "unimplemented",
            supports_resume_thread=False,
            supports_streaming_logs=False,
            supports_cancel=False,
            supports_usage=False,
            supports_read_only=implemented,
            supports_workspace_write=implemented,
            supports_network_access=False,
            notes=_codex_sdk_notes(sdk_available=sdk_available, implemented=implemented),
        )
    return BackendCapability(
        provider=provider,
        available=False,
        implemented=False,
        stability="unknown",
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
    capability = describe_backend_capability(provider, sdk_available=sdk_available)
    if provider == "codex_sdk" and fallback == "codex_exec" and not capability.implemented:
        return "codex_exec"
    return provider


def _codex_sdk_notes(*, sdk_available: bool, implemented: bool) -> list[str]:
    if implemented:
        return ["SDK backend implementation is enabled"]
    if sdk_available:
        return [
            "SDK import is available but Coductor SDK backend is not implemented yet",
            "configure fallback=codex_exec or use provider=codex_exec",
        ]
    return [
        "SDK import unavailable",
        "configure fallback=codex_exec or use provider=codex_exec",
    ]
