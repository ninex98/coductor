"""Planning node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    ExecutionPlanData,
    RepositorySnapshotData,
    SpecificationData,
)
from coductor.domain.enums import ArtifactType, ExecutionMode, RunStatus
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def create_execution_plan_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    spec: ArtifactEnvelope[SpecificationData] | None = None,
    snapshot: ArtifactEnvelope[RepositorySnapshotData] | None = None,
    requested_mode: ExecutionMode | None = None,
) -> dict[str, Any]:
    if context is not None:
        if state.status == RunStatus.HUMAN_REQUIRED:
            context.save(state)
            return {
                "current_stage": state.current_stage,
                "status": state.status,
                "last_error": state.last_error,
            }
        if spec is None or snapshot is None:
            raise ValueError("create_execution_plan_node requires spec and snapshot artifacts")
        plan_path = "03_execution_plan.yaml"
        if (context.repo.root / plan_path).exists():
            plan = ArtifactEnvelope[ExecutionPlanData].model_validate(
                context.repo.read(plan_path, ArtifactType.EXECUTION_PLAN).model_dump(
                    mode="json"
                )
            )
        else:
            plan = context.artifacts.write_plan(
                context.repo,
                state.run_id,
                spec,
                snapshot,
                requested_mode or context.requested_mode(state),
            )
        state.artifacts["03_execution_plan"] = "03_execution_plan.yaml"
        state.current_stage = "create_execution_plan"
        if not plan.data.validation.valid:
            state.status = RunStatus.HUMAN_REQUIRED
            state.current_stage = "human_required"
            state.last_error = "plan validation failed"
        elif plan.data.approval.required and not plan.data.approval.approved_by:
            state.status = RunStatus.HUMAN_REQUIRED
            state.current_stage = "human_required"
            state.last_error = "parallel plan approval required"
        context.save(state)
        patch: dict[str, Any] = {
            "current_stage": "create_execution_plan",
            "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
        }
        if state.status == RunStatus.HUMAN_REQUIRED:
            patch["current_stage"] = state.current_stage
            patch["status"] = state.status
            patch["last_error"] = state.last_error
        return patch
    return {
        "current_stage": "create_execution_plan",
        "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
    }
