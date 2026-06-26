"""Specification node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, GoalData, RepositorySnapshotData
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
        if goal is None or snapshot is None:
            raise ValueError("draft_spec_node requires goal and snapshot artifacts")
        context.artifacts.write_spec(context.repo, state.run_id, goal, snapshot)
        state.artifacts["02_spec"] = "02_spec.yaml"
        state.current_stage = "create_execution_plan"
        context.save(state)
        return {
            "current_stage": "create_execution_plan",
            "artifacts": {"02_spec": "02_spec.yaml"},
        }
    return {"current_stage": "draft_spec", "artifacts": {"02_spec": "02_spec.yaml"}}
