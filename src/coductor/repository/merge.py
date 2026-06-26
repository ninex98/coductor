"""Integration report helpers for completed task batches."""

from __future__ import annotations

from pathlib import Path

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import FileReference, IntegrationData
from coductor.domain.enums import ExecutionStrategy


def build_integration_data(
    strategy: ExecutionStrategy,
    completed_task_ids: list[str],
    *,
    run_dir: Path | None = None,
) -> IntegrationData:
    if strategy == ExecutionStrategy.SOLO:
        return IntegrationData(
            status="skipped",
            reason="solo strategy does not require multi-worktree integration",
        )
    reason = (
        "parallel tasks merged without conflicts"
        if strategy == ExecutionStrategy.PARALLEL
        else "pipeline tasks integrated after dependency order completed"
    )
    return IntegrationData(
        status="merged",
        reason=reason,
        merged_tasks=completed_task_ids,
        conflicts=[],
        worktree_diffs=_worktree_diffs(run_dir, completed_task_ids),
    )


def _worktree_diffs(run_dir: Path | None, completed_task_ids: list[str]) -> list[FileReference]:
    if run_dir is None:
        return []
    diffs: list[FileReference] = []
    for task_id in completed_task_ids:
        relative = f"tasks/{task_id}/patch.diff"
        path = run_dir / relative
        if not path.exists() or path.stat().st_size == 0:
            continue
        diffs.append(
            FileReference(
                path=relative,
                sha256=file_sha256(path),
                bytes=path.stat().st_size,
            )
        )
    return diffs
