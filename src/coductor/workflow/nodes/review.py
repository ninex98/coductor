"""Review node helpers."""

from __future__ import annotations

from collections.abc import Callable

from coductor.artifacts.models import ArtifactEnvelope, ReviewReportData
from coductor.domain.enums import ArtifactType
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def run_independent_review_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
    review: Callable[[], ArtifactEnvelope[ReviewReportData]] | None = None,
) -> dict[str, object]:
    if context is not None:
        review_path = "06_review.yaml"
        if (context.repo.root / review_path).exists():
            review_report = ArtifactEnvelope[ReviewReportData].model_validate(
                context.repo.read(review_path, ArtifactType.REVIEW_REPORT).model_dump(
                    mode="json"
                )
            )
            state.artifacts["06_review"] = review_path
            state.current_stage = "run_independent_review"
            state.review_passed = not review_report.data.requires_repair
            context.save(state)
            return {
                "current_stage": "run_independent_review",
                "artifacts": {"06_review": review_path},
                "review_passed": state.review_passed,
            }
        if review is None:
            raise ValueError("run_independent_review_node requires review callback")
        review_report = review()
        state.artifacts["06_review"] = "06_review.yaml"
        state.current_stage = "run_independent_review"
        state.review_passed = not review_report.data.requires_repair
        context.save(state)
        return {
            "current_stage": "run_independent_review",
            "artifacts": {"06_review": "06_review.yaml"},
            "review_passed": state.review_passed,
        }
    return {
        "current_stage": "run_independent_review",
        "artifacts": {"06_review": "06_review.yaml"},
    }


def review_next_stage(review: ReviewReportData) -> str:
    del review
    return "prepare_evidence"
