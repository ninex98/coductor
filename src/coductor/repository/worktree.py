"""Worktree extension points for later parallel execution."""

from __future__ import annotations

from pathlib import Path


class WorktreeManager:
    def __init__(self, root: Path) -> None:
        self.root = root

    def is_available(self) -> bool:
        return (self.root / ".git").exists()
