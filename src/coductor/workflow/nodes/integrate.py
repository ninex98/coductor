"""Integration node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.workflow.nodes.idempotency import reuse_existing_artifact
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def integrate_changes_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    plan: ArtifactEnvelope[Any] | None = None,
    completed_task_ids: list[str] | None = None,
    verification: WorkflowVerificationService | None = None,
) -> dict[str, Any]:
    if context is not None:
        existing = reuse_existing_artifact(
            state,
            context,
            artifact_key="04_integration",
            artifact_path="04_integration.yaml",
            next_stage="run_quality_gates",
        )
        if existing is not None:
            return existing
        if plan is None or verification is None:
            raise ValueError("integrate_changes_node requires plan and verification service")
        verification.write_integration(
            context.repo,
            state.run_id,
            plan,
            completed_task_ids or [],
        )
        state.artifacts["04_integration"] = "04_integration.yaml"
        state.current_stage = "run_quality_gates"
        context.save(state)
        return {
            "current_stage": "run_quality_gates",
            "artifacts": {"04_integration": "04_integration.yaml"},
        }
    return {
        "current_stage": "integrate_changes",
        "artifacts": {"04_integration": "04_integration.yaml"},
    }
