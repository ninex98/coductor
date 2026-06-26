"""Repair node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def repair_failure_node(state: WorkflowState) -> dict[str, Any]:
    return {
        "current_stage": "repair_failure",
        "repair_attempts": state.repair_attempts + 1,
        "gate_passed": True,
    }
