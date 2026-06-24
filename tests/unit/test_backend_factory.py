from __future__ import annotations

import pytest

from coductor.backends import factory
from coductor.backends.codex_exec import CodexExecBackend
from coductor.backends.codex_sdk import CodexSdkBackend
from coductor.backends.factory import create_backend
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.exceptions import BackendUnavailableError


def test_backend_factory_selects_fake() -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"

    backend = create_backend(config)

    assert isinstance(backend, FakeCodingBackend)


def test_backend_factory_selects_codex_exec() -> None:
    config = CoductorConfig.default()
    config.backend.provider = "codex_exec"

    backend = create_backend(config)

    assert isinstance(backend, CodexExecBackend)


def test_backend_factory_falls_back_to_codex_exec_when_sdk_unavailable() -> None:
    config = CoductorConfig.default()
    config.backend.provider = "codex_sdk"
    config.backend.fallback = "codex_exec"

    backend = create_backend(config, sdk_available=False)

    assert isinstance(backend, CodexExecBackend)


def test_backend_factory_auto_falls_back_when_sdk_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "codex_sdk"
    config.backend.fallback = "codex_exec"
    monkeypatch.setattr(factory, "is_codex_sdk_available", lambda: False)

    backend = create_backend(config)

    assert isinstance(backend, CodexExecBackend)


def test_backend_factory_selects_sdk_when_available() -> None:
    config = CoductorConfig.default()
    config.backend.provider = "codex_sdk"

    backend = create_backend(config, sdk_available=True)

    assert isinstance(backend, CodexSdkBackend)


def test_backend_factory_rejects_unknown_provider() -> None:
    config = CoductorConfig.default()
    config.backend.provider = "unknown"

    with pytest.raises(BackendUnavailableError, match="unknown backend provider"):
        create_backend(config)
