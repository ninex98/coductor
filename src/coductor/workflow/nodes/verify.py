"""Verification node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def run_quality_gates_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {
        "current_stage": "run_quality_gates",
        "artifacts": {"05_gate_report": "05_gate_report.yaml"},
    }
