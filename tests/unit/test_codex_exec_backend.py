from __future__ import annotations

from pathlib import Path

import pytest

from coductor.backends.codex_exec import CodexExecBackend
from coductor.domain.enums import SandboxMode
from coductor.exceptions import BackendUnavailableError


def test_codex_exec_uses_explicit_sandbox_without_cli_schema_mode(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="codex", schemas_dir=tmp_path)
    command = backend.build_command(
        prompt_path=tmp_path / "prompt.md",
        sandbox="workspace-write",
        output_schema="worker_result",
    )

    assert command[:2] == ["codex", "exec"]
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert "--output-schema" not in command


def test_codex_exec_maps_internal_sandbox_values_to_cli_values(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="codex", schemas_dir=tmp_path)

    command = backend.build_command(
        prompt_path=tmp_path / "prompt.md",
        sandbox=SandboxMode.READ_ONLY,
        output_schema="review_report",
    )

    assert command[command.index("--sandbox") + 1] == "read-only"


def test_codex_exec_command_uses_stdin_prompt(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="codex", schemas_dir=tmp_path)

    command = backend.build_command(
        prompt_path=tmp_path / "prompt.md",
        sandbox=SandboxMode.WORKSPACE_WRITE,
        output_schema=tmp_path / "custom.schema.json",
    )

    assert "--json" not in command
    assert "--skip-git-repo-check" in command
    assert command[-1] == "-"


def test_codex_exec_reports_missing_cli(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="definitely-missing-codex", schemas_dir=tmp_path)

    with pytest.raises(BackendUnavailableError, match="Codex CLI executable not found"):
        backend.continue_worker(
            backend.start_worker(
                request=_request(tmp_path),
            ),
            _request(tmp_path),
        )


def test_codex_exec_uses_request_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult

    received: dict[str, int] = {}

    def fake_run(*args, **kwargs):
        del args
        received["timeout"] = kwargs["timeout"]

        class Completed:
            stdout = "ok"
            stderr = ""
            returncode = 0

        return Completed()

    monkeypatch.setattr("coductor.backends.codex_exec.subprocess.run", fake_run)
    backend = CodexExecBackend(codex_bin="codex", schemas_dir=tmp_path)
    request = WorkerRequest(
        worker_id="worker_T001",
        role="builder",
        prompt="hello",
        workspace_path=tmp_path.as_posix(),
        sandbox=SandboxMode.WORKSPACE_WRITE,
        timeout_seconds=120,
    )

    result = backend.continue_worker(
        WorkerHandle(worker_id="worker_T001", thread_id="thread_1"),
        request,
    )

    assert isinstance(result, WorkerResult)
    assert received["timeout"] == 120


def _request(tmp_path: Path):
    from coductor.backends.base import WorkerRequest

    return WorkerRequest(
        worker_id="worker_T001",
        role="builder",
        prompt="hello",
        workspace_path=tmp_path.as_posix(),
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )
