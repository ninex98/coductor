"""Verification node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, GateReportData
from coductor.domain.enums import ArtifactType, RunStatus
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
        gate_path = "05_gate_report.yaml"
        if (context.repo.root / gate_path).exists() and not _has_repair_result(state):
            gate_report = ArtifactEnvelope[GateReportData].model_validate(
                context.repo.read(gate_path, ArtifactType.GATE_REPORT).model_dump(
                    mode="json"
                )
            )
            state.artifacts["05_gate_report"] = gate_path
            state.current_stage = "run_quality_gates"
            state.gate_passed = gate_report.data.required_gates_passed
            stopped = _should_stop_for_gate_failure(state, gate_report)
            if stopped:
                state.status = RunStatus.HUMAN_REQUIRED
                state.current_stage = "human_required"
                state.last_error = "质量门失败且达到停止规则"
            context.save(state)
            reuse_patch: dict[str, Any] = {
                "current_stage": state.current_stage,
                "artifacts": {"05_gate_report": gate_path},
                "gate_passed": state.gate_passed,
            }
            if stopped:
                reuse_patch["status"] = state.status
                reuse_patch["last_error"] = state.last_error
            return reuse_patch
        if verification is None:
            raise ValueError("run_quality_gates_node requires verification service")
        gate_report = verification.run_gates(context.repo, state.run_id)
        state.artifacts["05_gate_report"] = "05_gate_report.yaml"
        state.current_stage = "run_quality_gates"
        state.gate_passed = gate_report.data.required_gates_passed
        stopped = _should_stop_for_gate_failure(state, gate_report)
        if stopped:
            gate_report.data.next_action = "human_required"
            context.repo.write("05_gate_report.yaml", gate_report)
            state.status = RunStatus.HUMAN_REQUIRED
            state.current_stage = "human_required"
            state.last_error = "质量门失败且达到停止规则"
        context.save(state)
        run_patch: dict[str, Any] = {
            "current_stage": state.current_stage,
            "artifacts": {"05_gate_report": "05_gate_report.yaml"},
            "gate_passed": gate_report.data.required_gates_passed,
        }
        if stopped:
            run_patch["status"] = state.status
            run_patch["last_error"] = state.last_error
        return run_patch
    return {
        "current_stage": "run_quality_gates",
        "artifacts": {"05_gate_report": "05_gate_report.yaml"},
    }


def _should_stop_for_gate_failure(
    state: WorkflowState,
    gate_report: ArtifactEnvelope[GateReportData],
) -> bool:
    return (
        not gate_report.data.required_gates_passed
        and state.repair_attempts >= state.max_repair_attempts
    )


def _has_repair_result(state: WorkflowState) -> bool:
    return any(key.startswith("repair_result_") for key in state.artifacts)
