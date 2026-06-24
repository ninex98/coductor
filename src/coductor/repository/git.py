"""Git helpers that never mutate repository state."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_output(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip()


def current_commit(root: Path) -> str:
    return git_output(root, ["rev-parse", "HEAD"]) or "NO_GIT_REPOSITORY"


def is_dirty(root: Path) -> bool:
    status = git_output(root, ["status", "--porcelain"])
    return bool(status)
