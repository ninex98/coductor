"""Runtime dependencies for executable workflow nodes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import ExecutionMode
from coductor.services.review_delivery_service import ReviewDeliveryService
from coductor.services.task_execution_service import TaskExecutionService
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter, utc_now
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.state import WorkflowState


@dataclass(frozen=True)
class WorkflowRuntimeContext:
    repo: ArtifactRepository
    artifacts: WorkflowArtifactWriter
    checkpoints: WorkflowCheckpointStore
    task_execution: TaskExecutionService | None = None
    verification: WorkflowVerificationService | None = None
    review_delivery: ReviewDeliveryService | None = None
    on_dispatch: Callable[[str], None] | None = None

    def requested_mode(self, state: WorkflowState) -> ExecutionMode:
        return ExecutionMode(state.requested_mode)

    def save(self, state: WorkflowState) -> None:
        self.checkpoints.save(state, utc_now())
