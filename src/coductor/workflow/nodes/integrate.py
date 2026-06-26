"""Integration node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def integrate_changes_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {
        "current_stage": "integrate_changes",
        "artifacts": {"04_integration": "04_integration.yaml"},
    }
