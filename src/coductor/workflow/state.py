"""Workflow state for LangGraph-compatible orchestration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from coductor.domain.enums import RunStatus


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
    artifacts: dict[str, str] = {}
    stale_artifacts: list[str] = []
    updated_at: str | None = None
