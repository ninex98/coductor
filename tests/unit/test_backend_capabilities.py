from __future__ import annotations

from coductor.backends.capabilities import describe_backend_capability


def test_backend_capabilities_describe_fake_and_codex_exec() -> None:
    fake = describe_backend_capability("fake", sdk_available=False)
    codex_exec = describe_backend_capability("codex_exec", sdk_available=False)

    assert fake.provider == "fake"
    assert fake.available is True
    assert fake.supports_resume_thread is True
    assert fake.supports_usage is False
    assert codex_exec.provider == "codex_exec"
    assert codex_exec.available is True
    assert codex_exec.supports_workspace_write is True
    assert codex_exec.supports_network_access is False


def test_codex_sdk_capability_tracks_sdk_availability() -> None:
    missing = describe_backend_capability("codex_sdk", sdk_available=False)
    present = describe_backend_capability("codex_sdk", sdk_available=True)

    assert missing.available is False
    assert present.available is True
    assert present.supports_resume_thread is True
