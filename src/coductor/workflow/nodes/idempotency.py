"""Helpers for idempotent node resume behavior."""

from __future__ import annotations

from typing import Any

from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def reuse_existing_artifact(
    state: WorkflowState,
    context: WorkflowRuntimeContext,
    *,
    artifact_key: str,
    artifact_path: str,
    next_stage: str,
) -> dict[str, Any] | None:
    if not (context.repo.root / artifact_path).exists():
        return None
    state.artifacts[artifact_key] = artifact_path
    state.current_stage = next_stage
    context.save(state)
    return {
        "current_stage": next_stage,
        "artifacts": {artifact_key: artifact_path},
    }
