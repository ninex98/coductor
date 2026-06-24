"""Git worktree helpers for isolated parallel task execution."""

from __future__ import annotations

import subprocess
from pathlib import Path


class WorktreeManager:
    def __init__(self, root: Path) -> None:
        self.root = root

    def is_available(self) -> bool:
        return (self.root / ".git").exists()

    def path_for(self, run_id: str, task_id: str) -> Path:
        return self.root / ".coductor" / "worktrees" / run_id / task_id

    def create(self, run_id: str, task_id: str, base_ref: str) -> Path:
        path = self.path_for(run_id, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", path.as_posix(), base_ref],
            cwd=self.root,
            check=True,
        )
        return path

    def remove(self, run_id: str, task_id: str) -> None:
        path = self.path_for(run_id, task_id)
        subprocess.run(
            ["git", "worktree", "remove", path.as_posix(), "--force"],
            cwd=self.root,
            check=True,
        )

    def diff(self, run_id: str, task_id: str) -> Path:
        path = self.path_for(run_id, task_id)
        completed = subprocess.run(
            ["git", "-C", path.as_posix(), "diff", "--binary"],
            capture_output=True,
            text=True,
            check=False,
        )
        diff_path = path.with_suffix(".diff")
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(completed.stdout, encoding="utf-8")
        return diff_path
