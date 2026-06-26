"""Goal intake node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def collect_goal_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {"current_stage": "collect_goal", "artifacts": {"00_goal": "00_goal.yaml"}}
