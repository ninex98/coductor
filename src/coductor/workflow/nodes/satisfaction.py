"""Goal satisfaction evaluation node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    GateReportData,
    GoalSatisfactionReportData,
    SpecificationData,
    VerificationPlanData,
)
from coductor.domain.enums import ArtifactType
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def evaluate_goal_satisfaction_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
) -> dict[str, Any]:
    if context is not None:
        satisfaction_path = "07_goal_satisfaction.yaml"
        if (context.repo.root / satisfaction_path).exists() and not _has_repair_result(state):
            report = ArtifactEnvelope[GoalSatisfactionReportData].model_validate(
                context.repo.read(
                    satisfaction_path,
                    ArtifactType.GOAL_SATISFACTION_REPORT,
                ).model_dump(mode="json")
            )
        else:
            verification_path = "03_verification_plan.yaml"
            if not (context.repo.root / verification_path).exists():
                spec = ArtifactEnvelope[SpecificationData].model_validate(
                    context.repo.read("02_spec.yaml", ArtifactType.SPECIFICATION).model_dump(
                        mode="json"
                    )
                )
                context.artifacts.write_verification_plan(context.repo, state.run_id, spec)
            verification_plan = ArtifactEnvelope[VerificationPlanData].model_validate(
                context.repo.read(
                    verification_path,
                    ArtifactType.VERIFICATION_PLAN,
                ).model_dump(mode="json")
            )
            gate_report = ArtifactEnvelope[GateReportData].model_validate(
                context.repo.read("05_gate_report.yaml", ArtifactType.GATE_REPORT).model_dump(
                    mode="json"
                )
            )
            report = context.artifacts.write_goal_satisfaction(
                context.repo,
                state.run_id,
                verification_plan,
                gate_report,
            )
        state.artifacts["07_goal_satisfaction"] = satisfaction_path
        state.current_stage = "evaluate_goal_satisfaction"
        state.goal_satisfied = report.data.verdict == "satisfied"
        if not state.goal_satisfied:
            fingerprint = _satisfaction_fingerprint(report)
            if report.data.requires_human:
                state.satisfaction_repair_attempts = state.max_repair_attempts
                state.last_error = "goal satisfaction requires human"
            elif (
                state.last_satisfaction_error == fingerprint
                and state.satisfaction_repair_attempts > 0
            ):
                state.satisfaction_repair_attempts = max(
                    state.satisfaction_repair_attempts,
                    state.max_repair_attempts,
                )
                state.last_error = "repeated goal satisfaction failure"
            else:
                state.last_error = f"goal satisfaction {report.data.verdict}"
            state.last_satisfaction_error = fingerprint
        context.save(state)
        return {
            "current_stage": "evaluate_goal_satisfaction",
            "artifacts": {"07_goal_satisfaction": satisfaction_path},
            "goal_satisfied": state.goal_satisfied,
            "satisfaction_repair_attempts": state.satisfaction_repair_attempts,
            "last_satisfaction_error": state.last_satisfaction_error,
            "last_error": state.last_error,
        }
    return {
        "current_stage": "evaluate_goal_satisfaction",
        "artifacts": {"07_goal_satisfaction": "07_goal_satisfaction.yaml"},
    }


def _has_repair_result(state: WorkflowState) -> bool:
    return any(key.startswith("repair_result_") for key in state.artifacts)


def _satisfaction_fingerprint(
    report: ArtifactEnvelope[GoalSatisfactionReportData],
) -> str:
    return "|".join(
        ":".join(
            [
                result.criterion_id,
                result.status,
                ",".join(sorted(result.missing_evidence)),
                result.reason,
            ]
        )
        for result in report.data.criterion_results
        if result.status != "satisfied"
    )
