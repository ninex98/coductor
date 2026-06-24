from __future__ import annotations

from pathlib import Path

from coductor.backends.codex_exec import CodexExecBackend
from coductor.domain.enums import SandboxMode


def test_codex_exec_uses_explicit_sandbox_and_schema(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="codex", schemas_dir=tmp_path)
    command = backend.build_command(
        prompt_path=tmp_path / "prompt.md",
        sandbox="workspace-write",
        output_schema="worker_result",
    )

    assert command[:2] == ["codex", "exec"]
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert "--output-schema" in command
    assert command[command.index("--output-schema") + 1] == (
        tmp_path / "worker_result.schema.json"
    ).as_posix()


def test_codex_exec_maps_internal_sandbox_values_to_cli_values(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="codex", schemas_dir=tmp_path)

    command = backend.build_command(
        prompt_path=tmp_path / "prompt.md",
        sandbox=SandboxMode.READ_ONLY,
        output_schema="review_report",
    )

    assert command[command.index("--sandbox") + 1] == "read-only"


def test_codex_exec_command_uses_jsonl_and_stdin_prompt(tmp_path: Path) -> None:
    backend = CodexExecBackend(codex_bin="codex", schemas_dir=tmp_path)

    command = backend.build_command(
        prompt_path=tmp_path / "prompt.md",
        sandbox=SandboxMode.WORKSPACE_WRITE,
        output_schema=tmp_path / "custom.schema.json",
    )

    assert "--json" in command
    assert command[-1] == "-"
