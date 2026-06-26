"""Executable workflow graph slices backed by YAML artifact services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    EvidenceBundleData,
    GateReportData,
    GoalData,
    RepositorySnapshotData,
    ReviewReportData,
    SpecificationData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import WorkerHandle
from coductor.domain.enums import ArtifactType, ExecutionMode, RunStatus
from coductor.services.repair_service import RepairService
from coductor.services.task_execution_service import ExecutedTask, TaskExecutionService
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter, utc_now
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.nodes import inspect, intake
from coductor.workflow.runtime import WorkflowRuntimeContext
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
        state.requested_mode = str(requested_mode)
        context = WorkflowRuntimeContext(
            repo=self.repo,
            artifacts=self.artifacts,
            checkpoints=self.checkpoints,
        )
        intake.collect_goal_node(
            state,
            context=context,
        )
        goal = ArtifactEnvelope[GoalData].model_validate(
            self.repo.read("00_goal.yaml", ArtifactType.GOAL).model_dump(mode="json")
        )

        inspect.inspect_repository_node(state, context=context, goal=goal)
        snapshot = ArtifactEnvelope[RepositorySnapshotData].model_validate(
            self.repo.read(
                "01_repository_snapshot.yaml",
                ArtifactType.REPOSITORY_SNAPSHOT,
            ).model_dump(mode="json")
        )

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

    def run_task_execution(
        self,
        state: WorkflowState,
        *,
        plan: ArtifactEnvelope[Any],
        tasks: TaskExecutionService,
        on_dispatch: Callable[[str, WorkerHandle], None] | None = None,
    ) -> tuple[list[ExecutedTask], WorkflowState]:
        def record_dispatch(task_id: str, worker_handle: WorkerHandle) -> None:
            if on_dispatch is not None:
                on_dispatch(task_id, worker_handle)
            del worker_handle
            state.artifacts[f"task_{task_id}"] = f"tasks/{task_id}/task.yaml"
            state.current_stage = "dispatch_tasks"
            self._save(state)
            state.artifacts[f"worker_result_{task_id}"] = (
                f"tasks/{task_id}/worker_result.yaml"
            )
            self._save(state)

        executed = tasks.execute_plan_tasks(
            self.repo,
            state.run_id,
            plan,
            on_dispatch=record_dispatch,
        )
        return executed, state

    def run_integration(
        self,
        state: WorkflowState,
        *,
        plan: ArtifactEnvelope[Any],
        completed_task_ids: list[str],
        verification: WorkflowVerificationService,
    ) -> WorkflowState:
        verification.write_integration(
            self.repo,
            state.run_id,
            plan,
            completed_task_ids,
        )
        state.artifacts["04_integration"] = "04_integration.yaml"
        state.current_stage = "run_quality_gates"
        self._save(state)
        return state

    def run_quality_gates(
        self,
        state: WorkflowState,
        *,
        verification: WorkflowVerificationService,
    ) -> tuple[ArtifactEnvelope[GateReportData], WorkflowState]:
        gate_report = verification.run_gates(self.repo, state.run_id)
        state.artifacts["05_gate_report"] = "05_gate_report.yaml"
        state.current_stage = "run_quality_gates"
        state.gate_passed = gate_report.data.required_gates_passed
        self._save(state)
        return gate_report, state

    def run_repair(
        self,
        state: WorkflowState,
        *,
        builder_handle: WorkerHandle,
        gate_report: ArtifactEnvelope[GateReportData],
        repair: RepairService,
        target_task_id: str,
    ) -> WorkflowState:
        state.repair_attempts += 1
        state.current_stage = "repair_failure"
        self._save(state)
        repair.repair(
            self.repo,
            state.run_id,
            builder_handle,
            gate_report,
            state.repair_attempts,
            target_task_id,
        )
        repair_id = f"R{state.repair_attempts:03d}"
        state.artifacts[f"repair_request_{repair_id}"] = (
            f"repairs/{repair_id}/repair_request.yaml"
        )
        state.artifacts[f"repair_result_{repair_id}"] = (
            f"repairs/{repair_id}/repair_result.yaml"
        )
        state.current_stage = "run_quality_gates"
        self._save(state)
        return state

    def run_review(
        self,
        state: WorkflowState,
        *,
        review: Callable[[], ArtifactEnvelope[ReviewReportData]],
    ) -> tuple[ArtifactEnvelope[ReviewReportData], WorkflowState]:
        review_report = review()
        state.artifacts["06_review"] = "06_review.yaml"
        state.current_stage = "run_independent_review"
        state.review_passed = not review_report.data.requires_repair
        self._save(state)
        return review_report, state

    def run_evidence(
        self,
        state: WorkflowState,
        *,
        evidence: Callable[[], ArtifactEnvelope[EvidenceBundleData]],
    ) -> tuple[ArtifactEnvelope[EvidenceBundleData], WorkflowState]:
        evidence_bundle = evidence()
        state.artifacts["07_evidence"] = "07_evidence.yaml"
        state.status = (
            RunStatus.READY_FOR_HUMAN_REVIEW
            if evidence_bundle.data.final_status == "ready_for_human_review"
            else RunStatus.HUMAN_REQUIRED
        )
        state.current_stage = "prepare_evidence"
        self._save(state)
        return evidence_bundle, state

    def _save(self, state: WorkflowState) -> None:
        self.checkpoints.save(state, utc_now())
