"""Planning node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    RepositorySnapshotData,
    SpecificationData,
)
from coductor.domain.enums import ExecutionMode
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
        if spec is None or snapshot is None:
            raise ValueError("create_execution_plan_node requires spec and snapshot artifacts")
        context.artifacts.write_plan(
            context.repo,
            state.run_id,
            spec,
            snapshot,
            requested_mode or context.requested_mode(state),
        )
        state.artifacts["03_execution_plan"] = "03_execution_plan.yaml"
        state.current_stage = "create_execution_plan"
        context.save(state)
        return {
            "current_stage": "create_execution_plan",
            "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
        }
    return {
        "current_stage": "create_execution_plan",
        "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
    }
