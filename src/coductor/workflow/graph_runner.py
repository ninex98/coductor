"""Executable workflow graph slices backed by YAML artifact services."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    GoalData,
    RepositorySnapshotData,
    SpecificationData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import ExecutionMode
from coductor.workflow.artifact_writer import WorkflowArtifactWriter, utc_now
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.state import WorkflowState


class WorkflowGraphRunner:
    def __init__(
        self,
        *,
        repo: ArtifactRepository,
        artifacts: WorkflowArtifactWriter,
        checkpoints: WorkflowCheckpointStore,
    ) -> None:
        self.repo = repo
        self.artifacts = artifacts
        self.checkpoints = checkpoints

    def run_front_half(
        self,
        state: WorkflowState,
        *,
        requested_mode: ExecutionMode,
    ) -> tuple[
        ArtifactEnvelope[GoalData],
        ArtifactEnvelope[RepositorySnapshotData],
        ArtifactEnvelope[SpecificationData],
        ArtifactEnvelope[Any],
        WorkflowState,
    ]:
        if state.raw_goal is None:
            raise ValueError("workflow state must include raw_goal")
        goal = self.artifacts.write_goal(
            self.repo,
            state.run_id,
            state.raw_goal,
            requested_mode,
        )
        state.artifacts["00_goal"] = "00_goal.yaml"
        state.current_stage = "inspect_repository"
        self._save(state)

        snapshot = self.artifacts.write_snapshot(self.repo, state.run_id, goal)
        state.artifacts["01_repository_snapshot"] = "01_repository_snapshot.yaml"
        state.current_stage = "draft_spec"
        self._save(state)

        spec = self.artifacts.write_spec(self.repo, state.run_id, goal, snapshot)
        state.artifacts["02_spec"] = "02_spec.yaml"
        state.current_stage = "create_execution_plan"
        self._save(state)

        plan = self.artifacts.write_plan(
            self.repo,
            state.run_id,
            spec,
            snapshot,
            requested_mode,
        )
        state.artifacts["03_execution_plan"] = "03_execution_plan.yaml"
        state.current_stage = "create_execution_plan"
        self._save(state)
        return goal, snapshot, spec, plan, state

    def _save(self, state: WorkflowState) -> None:
        self.checkpoints.save(state, utc_now())
