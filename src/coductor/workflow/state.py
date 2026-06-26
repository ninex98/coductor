"""Workflow state for LangGraph-compatible orchestration."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict

from coductor.domain.enums import RunStatus


def merge_artifacts(left: dict[str, str], right: dict[str, str] | None) -> dict[str, str]:
    if right is None:
        return left
    return {**left, **right}


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    run_id: str
    status: RunStatus = RunStatus.CREATED
    current_stage: str = "collect_goal"
    repair_attempts: int = 0
    last_error: str | None = None
    raw_goal: str | None = None
    requested_mode: str = "auto"
    run_dir: str | None = None
    artifacts: Annotated[dict[str, str], merge_artifacts] = {}
    completed_task_ids: list[str] = []
    stale_artifacts: list[str] = []
    updated_at: str | None = None
    gate_passed: bool = True
    max_repair_attempts: int = 0
    review_passed: bool = True
