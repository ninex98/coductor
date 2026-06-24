"""Approval service placeholder for future interrupts."""

from __future__ import annotations


class ApprovalService:
    def requires_human(self, unresolved_questions: list[str], approval_required: bool) -> bool:
        return bool(unresolved_questions) or approval_required
