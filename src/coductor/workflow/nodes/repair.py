"""Repair node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, GateReportData
from coductor.backends.base import WorkerHandle
from coductor.services.repair_service import RepairService
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def repair_failure_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    builder_handle: WorkerHandle | None = None,
    gate_report: ArtifactEnvelope[GateReportData] | None = None,
    repair: RepairService | None = None,
    target_task_id: str | None = None,
) -> dict[str, Any]:
    if context is not None:
        if (
            builder_handle is None
            or gate_report is None
            or repair is None
            or target_task_id is None
        ):
            raise ValueError("repair_failure_node requires repair context")
        state.repair_attempts += 1
        state.current_stage = "repair_failure"
        context.save(state)
        repair.repair(
            context.repo,
            state.run_id,
            builder_handle,
            gate_report,
            state.repair_attempts,
            target_task_id,
        )
        repair_id = f"R{state.repair_attempts:03d}"
        state.artifacts[f"repair_request_{repair_id}"] = (
            f"repairs/{repair_id}/repair_request.yaml"
        )
        state.artifacts[f"repair_result_{repair_id}"] = (
            f"repairs/{repair_id}/repair_result.yaml"
        )
        state.current_stage = "run_quality_gates"
        context.save(state)
        return {
            "current_stage": "run_quality_gates",
            "repair_attempts": state.repair_attempts,
            "artifacts": {
                f"repair_request_{repair_id}": f"repairs/{repair_id}/repair_request.yaml",
                f"repair_result_{repair_id}": f"repairs/{repair_id}/repair_result.yaml",
            },
        }
    return {
        "current_stage": "repair_failure",
        "repair_attempts": state.repair_attempts + 1,
        "gate_passed": True,
    }
