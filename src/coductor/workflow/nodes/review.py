"""Review node helpers."""

from __future__ import annotations

from coductor.artifacts.models import ReviewReportData
from coductor.workflow.state import WorkflowState


def run_independent_review_node(state: WorkflowState) -> dict[str, object]:
    del state
    return {
        "current_stage": "run_independent_review",
        "artifacts": {"06_review": "06_review.yaml"},
    }


def review_next_stage(review: ReviewReportData) -> str:
    del review
    return "prepare_evidence"
