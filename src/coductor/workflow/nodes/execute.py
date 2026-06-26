"""Task execution node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def materialize_tasks_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
) -> dict[str, Any]:
    if context is not None:
        state.current_stage = "materialize_tasks"
        context.save(state)
    return {"current_stage": "materialize_tasks"}


def dispatch_tasks_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
) -> dict[str, Any]:
    if context is not None:
        state.current_stage = "dispatch_tasks"
        context.save(state)
    return {"current_stage": "dispatch_tasks"}
