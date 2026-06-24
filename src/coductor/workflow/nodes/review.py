"""Review node helpers."""

from __future__ import annotations

from coductor.artifacts.models import ReviewReportData


def review_next_stage(review: ReviewReportData) -> str:
    del review
    return "prepare_evidence"
