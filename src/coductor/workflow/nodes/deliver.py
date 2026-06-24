"""Delivery node helpers."""

from __future__ import annotations

from coductor.artifacts.models import EvidenceBundleData, EvidenceValidation
from coductor.services.evidence_service import EvidenceCompletenessValidator


def validate_delivery(evidence: EvidenceBundleData) -> EvidenceValidation:
    return EvidenceCompletenessValidator().validate(evidence)
