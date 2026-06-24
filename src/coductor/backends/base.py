"""Coding backend interface and shared request/result models."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from coductor.domain.enums import SandboxMode, WorkerStatus


class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str
    role: str
    prompt: str
    workspace_path: str
    sandbox: SandboxMode
    thread_policy: str = "new"
    existing_thread_id: str | None = None


class WorkerHandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str
    thread_id: str


class WorkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str
    thread_id: str
    summary: str
    files_read: list[str] = []
    files_changed: list[str] = []
    commands_run: list[str] = []
    tests_claimed: list[str] = []
    generated_artifacts: list[str] = []
    unresolved_issues: list[str] = []
    exit_reason: str = "completed"


class CodingBackend(Protocol):
    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        ...

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        ...

    def cancel_worker(self, handle: WorkerHandle) -> None:
        ...

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        ...
