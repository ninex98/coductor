"""Repository inspection node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, GoalData
from coductor.workflow.nodes.idempotency import reuse_existing_artifact
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def inspect_repository_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    goal: ArtifactEnvelope[GoalData] | None = None,
) -> dict[str, Any]:
    if context is not None:
        existing = reuse_existing_artifact(
            state,
            context,
            artifact_key="01_repository_snapshot",
            artifact_path="01_repository_snapshot.yaml",
            next_stage="draft_spec",
        )
        if existing is not None:
            return existing
        if goal is None:
            raise ValueError("inspect_repository_node requires goal artifact")
        context.artifacts.write_snapshot(context.repo, state.run_id, goal)
        state.artifacts["01_repository_snapshot"] = "01_repository_snapshot.yaml"
        state.current_stage = "draft_spec"
        context.save(state)
        return {
            "current_stage": "draft_spec",
            "artifacts": {"01_repository_snapshot": "01_repository_snapshot.yaml"},
        }
    return {
        "current_stage": "inspect_repository",
        "artifacts": {"01_repository_snapshot": "01_repository_snapshot.yaml"},
    }
