"""Offline backend for tests, demos, and no-API runs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.domain.enums import WorkerStatus
from coductor.domain.ids import new_id


class FakeCodingBackend:
    def __init__(self, repair_side_effect: Callable[[], None] | None = None) -> None:
        self.repair_side_effect = repair_side_effect
        self.builder_thread_ids: list[str] = []
        self.review_thread_ids: list[str] = []
        self.handles: dict[str, WorkerHandle] = {}

    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        thread_id = new_id("thread")
        handle = WorkerHandle(worker_id=request.worker_id, thread_id=thread_id)
        self.handles[request.worker_id] = handle
        if request.role == "reviewer":
            self.review_thread_ids.append(thread_id)
        else:
            self.builder_thread_ids.append(thread_id)
        return handle

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        if request.role == "repairer" and self.repair_side_effect is not None:
            self.repair_side_effect()
        files_changed: list[str] = []
        if request.role in {"builder", "repairer"}:
            output = Path(request.workspace_path) / "coductor_fake_output.txt"
            output.write_text(
                f"{request.role} {request.worker_id} completed in {handle.thread_id}\n",
                encoding="utf-8",
            )
            files_changed.append(output.relative_to(request.workspace_path).as_posix())
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary=f"Fake backend completed {request.role} for {request.worker_id}",
            files_read=["00_goal.yaml", "02_spec.yaml"],
            files_changed=files_changed,
            commands_run=[],
            tests_claimed=[],
            generated_artifacts=[],
            unresolved_issues=[],
        )

    def cancel_worker(self, handle: WorkerHandle) -> None:
        self.handles.pop(handle.worker_id, None)

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.COMPLETED
