"""Delivery node helpers."""

from __future__ import annotations

from coductor.artifacts.models import EvidenceBundleData, EvidenceValidation
from coductor.domain.enums import RunStatus
from coductor.services.evidence_service import EvidenceCompletenessValidator
from coductor.workflow.state import WorkflowState


def prepare_evidence_node(state: WorkflowState) -> dict[str, object]:
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
