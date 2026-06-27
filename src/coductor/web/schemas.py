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
    validation: dict[str, Any]
    completed_tasks: list[str] = Field(default_factory=list)
    evidence_files: list[dict[str, Any]] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)
    known_risks: list[str] = Field(default_factory=list)


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
    release: ConsoleReleaseSummary | None = None


class ConsoleDoctorReport(BaseModel):
    checks: dict[str, Any]


class ConsoleActionResult(BaseModel):
    run_id: str
    action: str
    status: str
    message: str
    next_command: str | None = None
