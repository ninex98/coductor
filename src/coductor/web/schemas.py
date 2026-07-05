"""Typed models for the local web console API."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ConsoleError(BaseModel):
    message: str
    recoverable: bool = True
    next_command: str | None = None


class ConsoleResponse(BaseModel, Generic[DataT]):  # noqa: UP046
    ok: bool
    data: DataT | None = None
    error: ConsoleError | None = None


class ConsoleHealth(BaseModel):
    root: str
    version: str


class ConsoleEvent(BaseModel):
    stage: str
    message: str
    created_at: str


class ConsoleRunSummary(BaseModel):
    run_id: str
    status: str
    run_dir: str
    updated_at: str
    current_stage: str | None = None
    last_error: str | None = None
    run_dir_valid: bool = True
    run_dir_error: str | None = None


class ConsoleCheckpointSummary(BaseModel):
    current_stage: str
    completed_task_ids: list[str] = Field(default_factory=list)
    last_error: str | None = None
    stale_artifacts: list[str] = Field(default_factory=list)


class ConsoleArtifactSummary(BaseModel):
    path: str
    artifact_type: str
    status: str
    revision: int
    sha256: str
    producer: str


class ConsoleArtifactDetail(ConsoleArtifactSummary):
    raw_text: str
    parsed_yaml: dict[str, Any]
    truncated: bool
    inputs: list[dict[str, Any]] = Field(default_factory=list)


class ConsoleTextFile(BaseModel):
    path: str
    raw_text: str
    truncated: bool = False


class ConsoleEvidenceSummary(BaseModel):
    final_status: str
    gate_summary: dict[str, Any]
    review_summary: dict[str, Any]
    goal_satisfaction: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any]
    completed_tasks: list[str] = Field(default_factory=list)
    evidence_files: list[dict[str, Any]] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)
    known_risks: list[str] = Field(default_factory=list)


class ConsoleGoalCriterionSummary(BaseModel):
    criterion_id: str
    description: str | None = None
    verification: str | None = None
    tool: str | None = None
    required: bool = True
    status: str = "unknown"
    evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    reason: str | None = None


class ConsoleToolEvidenceSummary(BaseModel):
    path: str
    check_id: str
    tool_run_id: str
    tool: str
    required: bool
    status: str
    command: str
    duration_ms: int = 0
    stdout_path: str
    stderr_path: str
    artifacts: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    observations: dict[str, Any] = Field(default_factory=dict)
    failure_fingerprint: str | None = None


class ConsoleRepairSummary(BaseModel):
    path: str
    reason: str
    attempt: int
    max_attempts: int
    missing_criteria: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    recommended_action: str | None = None


class ConsoleGoalLoopSummary(BaseModel):
    verdict: str = "pending"
    satisfied: int = 0
    not_satisfied: int = 0
    uncertain: int = 0
    unknown: int = 0
    planned_criteria: int = 0
    all_required_criteria_planned: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    repair_recommendation: str | None = None
    requires_repair: bool = False
    requires_human: bool = False
    goal_iteration: int = 0
    satisfaction_repair_attempts: int = 0
    last_satisfaction_error: str | None = None
    stale_artifacts: list[str] = Field(default_factory=list)
    criteria: list[ConsoleGoalCriterionSummary] = Field(default_factory=list)
    tools: list[ConsoleToolEvidenceSummary] = Field(default_factory=list)
    repairs: list[ConsoleRepairSummary] = Field(default_factory=list)


class ConsoleReleaseSummary(BaseModel):
    status: str
    ready: bool
    reasons: list[str] = Field(default_factory=list)
    remote_actions_allowed: bool = False
    local_commands: list[str] = Field(default_factory=list)
    manual_commands: list[str] = Field(default_factory=list)


class ConsoleRunDetail(ConsoleRunSummary):
    checkpoint: ConsoleCheckpointSummary | None = None
    events: list[ConsoleEvent] = Field(default_factory=list)
    artifacts: list[ConsoleArtifactSummary] = Field(default_factory=list)
    evidence: ConsoleEvidenceSummary | None = None
    goal_loop: ConsoleGoalLoopSummary | None = None
    release: ConsoleReleaseSummary | None = None


class ConsoleDoctorReport(BaseModel):
    checks: dict[str, Any]


class ConsoleActionResult(BaseModel):
    run_id: str
    action: str
    status: str
    message: str
    next_command: str | None = None
