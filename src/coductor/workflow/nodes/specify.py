"""Specification node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    GoalData,
    RepositorySnapshotData,
    SpecificationData,
)
from coductor.domain.enums import ArtifactType, RunStatus
from coductor.workflow.nodes.idempotency import reuse_existing_artifact
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def draft_spec_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    goal: ArtifactEnvelope[GoalData] | None = None,
    snapshot: ArtifactEnvelope[RepositorySnapshotData] | None = None,
) -> dict[str, Any]:
    if context is not None:
        existing = reuse_existing_artifact(
            state,
            context,
            artifact_key="02_spec",
            artifact_path="02_spec.yaml",
            next_stage="create_execution_plan",
        )
        if existing is not None:
            if _spec_approval_required(context, state):
                return _stop_for_spec_approval(state, context)
            return existing
        if goal is None or snapshot is None:
            raise ValueError("draft_spec_node requires goal and snapshot artifacts")
        context.artifacts.write_spec(context.repo, state.run_id, goal, snapshot)
        state.artifacts["02_spec"] = "02_spec.yaml"
        if _spec_approval_required(context, state):
            return _stop_for_spec_approval(state, context)
        state.current_stage = "create_execution_plan"
        context.save(state)
        return {
            "current_stage": "create_execution_plan",
            "artifacts": {"02_spec": "02_spec.yaml"},
        }
    return {"current_stage": "draft_spec", "artifacts": {"02_spec": "02_spec.yaml"}}


def _spec_approval_required(
    context: WorkflowRuntimeContext,
    state: WorkflowState,
) -> bool:
    if not context.artifacts.config.workflow.require_spec_approval:
        return False
    spec = ArtifactEnvelope[SpecificationData].model_validate(
        context.repo.read("02_spec.yaml", ArtifactType.SPECIFICATION).model_dump(mode="json")
    )
    return spec.data.approval.required and not spec.data.approval.approved_by


def _stop_for_spec_approval(
    state: WorkflowState,
    context: WorkflowRuntimeContext,
) -> dict[str, Any]:
    state.status = RunStatus.HUMAN_REQUIRED
    state.current_stage = "human_required"
    state.last_error = "spec approval required"
    context.save(state)
    return {
        "current_stage": "human_required",
        "status": state.status,
        "last_error": state.last_error,
        "artifacts": {"02_spec": "02_spec.yaml"},
    }
