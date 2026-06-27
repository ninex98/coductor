"""Delivery node helpers."""

from __future__ import annotations

from collections.abc import Callable

from coductor.artifacts.models import ArtifactEnvelope, EvidenceBundleData, EvidenceValidation
from coductor.domain.enums import ArtifactType, RunStatus
from coductor.services.evidence_service import EvidenceCompletenessValidator
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def prepare_evidence_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    evidence: Callable[[], ArtifactEnvelope[EvidenceBundleData]] | None = None,
) -> dict[str, object]:
    if context is not None:
        evidence_path = "07_evidence.yaml"
        if (context.repo.root / evidence_path).exists():
            evidence_bundle = ArtifactEnvelope[EvidenceBundleData].model_validate(
                context.repo.read(evidence_path, ArtifactType.EVIDENCE_BUNDLE).model_dump(
                    mode="json"
                )
            )
            state.artifacts["07_evidence"] = evidence_path
            state.status = (
                RunStatus.READY_FOR_HUMAN_REVIEW
                if evidence_bundle.data.final_status == "ready_for_human_review"
                else RunStatus.HUMAN_REQUIRED
            )
            state.current_stage = "prepare_evidence"
            context.save(state)
            return {
                "current_stage": "prepare_evidence",
                "status": state.status,
                "artifacts": {"07_evidence": evidence_path},
            }
        if evidence is None:
            raise ValueError("prepare_evidence_node requires evidence callback")
        evidence_bundle = evidence()
        state.artifacts["07_evidence"] = "07_evidence.yaml"
        state.status = (
            RunStatus.READY_FOR_HUMAN_REVIEW
            if evidence_bundle.data.final_status == "ready_for_human_review"
            else RunStatus.HUMAN_REQUIRED
        )
        state.current_stage = "prepare_evidence"
        context.save(state)
        return {
            "current_stage": "prepare_evidence",
            "status": state.status,
            "artifacts": {"07_evidence": "07_evidence.yaml"},
        }
    status = (
        RunStatus.READY_FOR_HUMAN_REVIEW
        if state.status == RunStatus.RUNNING
        else state.status
    )
    return {
        "current_stage": "prepare_evidence",
        "status": status,
        "artifacts": {"07_evidence": "07_evidence.yaml"},
    }


def validate_delivery(evidence: EvidenceBundleData) -> EvidenceValidation:
    return EvidenceCompletenessValidator().validate(evidence)
