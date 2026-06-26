"""Goal intake node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def collect_goal_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
) -> dict[str, Any]:
    if context is not None:
        if state.raw_goal is None:
            raise ValueError("workflow state must include raw_goal")
        context.artifacts.write_goal(
            context.repo,
            state.run_id,
            state.raw_goal,
            context.requested_mode(state),
        )
        state.artifacts["00_goal"] = "00_goal.yaml"
        state.current_stage = "inspect_repository"
        context.save(state)
        return {"current_stage": "inspect_repository", "artifacts": {"00_goal": "00_goal.yaml"}}
    return {"current_stage": "collect_goal", "artifacts": {"00_goal": "00_goal.yaml"}}
