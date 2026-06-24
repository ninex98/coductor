"""Routing helpers for the workflow graph."""

from __future__ import annotations

from coductor.artifacts.models import GateReportData, ReviewReportData


def route_after_gates(report: GateReportData) -> str:
    return "run_independent_review" if report.required_gates_passed else report.next_action


def route_after_review(review: ReviewReportData) -> str:
    if not review.requires_repair and review.blocking_findings == 0:
        return "prepare_evidence"
    return "repair_failure"
