"""Runtime dependencies for executable workflow nodes."""

from __future__ import annotations

from dataclasses import dataclass

from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import ExecutionMode
from coductor.workflow.artifact_writer import WorkflowArtifactWriter, utc_now
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.state import WorkflowState


@dataclass(frozen=True)
class WorkflowRuntimeContext:
    repo: ArtifactRepository
    artifacts: WorkflowArtifactWriter
    checkpoints: WorkflowCheckpointStore

    def requested_mode(self, state: WorkflowState) -> ExecutionMode:
        return ExecutionMode(state.requested_mode)

    def save(self, state: WorkflowState) -> None:
        self.checkpoints.save(state, utc_now())
