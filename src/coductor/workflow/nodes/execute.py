"""Task execution node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def materialize_tasks_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {"current_stage": "materialize_tasks"}


def dispatch_tasks_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {"current_stage": "dispatch_tasks"}
