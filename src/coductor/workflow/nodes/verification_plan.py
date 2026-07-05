"""Verification planning node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, SpecificationData, VerificationPlanData
from coductor.domain.enums import ArtifactType
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def create_verification_plan_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    spec: ArtifactEnvelope[SpecificationData] | None = None,
) -> dict[str, Any]:
    if context is not None:
        if spec is None:
            raise ValueError("create_verification_plan_node requires spec artifact")
        plan_path = "03_verification_plan.yaml"
        if (context.repo.root / plan_path).exists():
            ArtifactEnvelope[VerificationPlanData].model_validate(
                context.repo.read(plan_path, ArtifactType.VERIFICATION_PLAN).model_dump(
                    mode="json"
                )
            )
        else:
            context.artifacts.write_verification_plan(context.repo, state.run_id, spec)
        state.artifacts["03_verification_plan"] = plan_path
        state.current_stage = "create_verification_plan"
        context.save(state)
        return {
            "current_stage": "create_verification_plan",
            "artifacts": {"03_verification_plan": plan_path},
        }
    return {
        "current_stage": "create_verification_plan",
        "artifacts": {"03_verification_plan": "03_verification_plan.yaml"},
    }
