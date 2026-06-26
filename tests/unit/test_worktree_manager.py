from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coductor.repository.worktree import WorktreeManager


def test_worktree_manager_builds_safe_paths(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path)

    path = manager.path_for("run_abc", "T001")

    assert path.as_posix().endswith(".coductor/worktrees/run_abc/T001")
    assert tmp_path in path.parents


def test_worktree_manager_uses_list_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="diff --git a/file b/file\n")

    monkeypatch.setattr("coductor.repository.worktree.subprocess.run", fake_run)
    manager = WorktreeManager(tmp_path)

    worktree_path = manager.create("run_abc", "T001", "HEAD")
    diff_path = manager.diff("run_abc", "T001")
    manager.apply(diff_path)
    manager.remove("run_abc", "T001")

    assert calls == [
        ["git", "worktree", "add", worktree_path.as_posix(), "HEAD"],
        ["git", "-C", worktree_path.as_posix(), "diff", "--binary"],
        ["git", "apply", "--3way", diff_path.as_posix()],
        ["git", "worktree", "remove", worktree_path.as_posix(), "--force"],
    ]
    assert diff_path == tmp_path / ".coductor/worktrees/run_abc/T001.diff"
    assert diff_path.read_text(encoding="utf-8") == "diff --git a/file b/file\n"
