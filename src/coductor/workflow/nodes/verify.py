"""Verification node helpers."""

from __future__ import annotations

from typing import Any

from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def run_quality_gates_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    verification: WorkflowVerificationService | None = None,
) -> dict[str, Any]:
    if context is not None:
        if verification is None:
            raise ValueError("run_quality_gates_node requires verification service")
        gate_report = verification.run_gates(context.repo, state.run_id)
        state.artifacts["05_gate_report"] = "05_gate_report.yaml"
        state.current_stage = "run_quality_gates"
        state.gate_passed = gate_report.data.required_gates_passed
        context.save(state)
        return {
            "current_stage": "run_quality_gates",
            "artifacts": {"05_gate_report": "05_gate_report.yaml"},
            "gate_passed": gate_report.data.required_gates_passed,
        }
    return {
        "current_stage": "run_quality_gates",
        "artifacts": {"05_gate_report": "05_gate_report.yaml"},
    }
