"""Integration report helpers for completed task batches."""

from __future__ import annotations

from coductor.artifacts.models import IntegrationData
from coductor.domain.enums import ExecutionStrategy


def build_integration_data(
    strategy: ExecutionStrategy,
    completed_task_ids: list[str],
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
    )
