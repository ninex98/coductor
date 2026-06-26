"""Planning node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def create_execution_plan_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {
        "current_stage": "create_execution_plan",
        "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
    }
