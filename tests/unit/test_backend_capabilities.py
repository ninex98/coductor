from __future__ import annotations

from coductor.backends.capabilities import (
    describe_backend_capability,
    effective_backend_provider,
)


def test_backend_capabilities_describe_fake_and_codex_exec() -> None:
    fake = describe_backend_capability("fake", sdk_available=False)
    codex_exec = describe_backend_capability("codex_exec", sdk_available=False)

    assert fake.provider == "fake"
    assert fake.available is True
    assert fake.implemented is True
    assert fake.stability == "test_only"
    assert fake.supports_resume_thread is True
    assert fake.supports_usage is False
    assert codex_exec.provider == "codex_exec"
    assert codex_exec.available is True
    assert codex_exec.implemented is True
    assert codex_exec.stability == "stable"
    assert codex_exec.supports_resume_thread is False
    assert codex_exec.supports_cancel is False
    assert codex_exec.supports_workspace_write is True
    assert codex_exec.supports_network_access is False


def test_codex_sdk_capability_is_not_claimed_until_backend_is_implemented() -> None:
    missing = describe_backend_capability("codex_sdk", sdk_available=False)
    present = describe_backend_capability("codex_sdk", sdk_available=True)

    assert missing.available is False
    assert missing.implemented is False
    assert present.available is True
    assert present.implemented is False
    assert present.stability == "unimplemented"
    assert present.supports_resume_thread is False
    assert present.supports_usage is False
    assert "not implemented yet" in " ".join(present.notes)


def test_effective_backend_falls_back_for_unimplemented_sdk() -> None:
    assert (
        effective_backend_provider(
            "codex_sdk",
            fallback="codex_exec",
            sdk_available=True,
        )
        == "codex_exec"
    )
