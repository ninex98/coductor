"""Phase 1 vertical workflow service."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    ArtifactMetadata,
    EvidenceBundleData,
    ExecutionPlanData,
    GateReportData,
    GoalData,
    Producer,
    ReviewReportData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.validator import ArtifactLineageValidator
from coductor.backends.base import CodingBackend, WorkerHandle
from coductor.backends.factory import create_backend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ExecutionStrategy,
    RunStatus,
)
from coductor.domain.ids import new_id
from coductor.domain.models import RunResult
from coductor.services.repair_service import RepairService
from coductor.services.review_delivery_service import ReviewDeliveryService
from coductor.services.task_execution_service import TaskExecutionService
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.storage.database import Database
from coductor.workflow.artifact_writer import WorkflowArtifactWriter
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.graph import build_workflow_graph
from coductor.workflow.langgraph_checkpoint import LangGraphCheckpointStore
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RunService:
    def __init__(
        self,
        root: Path,
        config: CoductorConfig,
        *,
        backend: CodingBackend | None = None,
        progress: Callable[[str, str], None] | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.coductor_dir = root / ".coductor"
        self.runs_dir = self.coductor_dir / "runs"
        self.db = Database(self.coductor_dir / "coductor.sqlite3")
        self.checkpoints = WorkflowCheckpointStore(self.db, self.runs_dir)
        self.langgraph_checkpoints = LangGraphCheckpointStore(self.db.path)
        self.backend = backend or self._backend_from_config()
        self.progress = progress
        self.artifacts = WorkflowArtifactWriter(root, config)
        self.task_execution = TaskExecutionService(root, config, self.backend, self.artifacts)
        self.verification = WorkflowVerificationService(root, config, self.artifacts)
        self.repairs = RepairService(root, config, self.backend, self.artifacts)
        self.review_delivery = ReviewDeliveryService(root, config, self.backend, self.artifacts)

    def run(
        self,
        raw_goal: str,
        *,
        mode: ExecutionMode | None = None,
        resume_run_id: str | None = None,
    ) -> RunResult:
        run_id = resume_run_id or new_id("run")
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        repo = ArtifactRepository(run_dir)
        requested_mode = mode or self.config.workflow.default_mode
        state = WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            repair_attempts=0,
            raw_goal=raw_goal,
            requested_mode=str(requested_mode),
            run_dir=run_dir.as_posix(),
            max_repair_attempts=self.config.workflow.max_repair_attempts,
        )
        return self._run_contextual_graph(
            state,
            repo=repo,
            run_dir=run_dir,
        )

    def _run_contextual_graph(
        self,
        state: WorkflowState,
        *,
        repo: ArtifactRepository,
        run_dir: Path,
    ) -> RunResult:
        run_id = state.run_id
        self.save_checkpoint(state)
        self._event(run_id, "collect_goal", "accepted user goal")
        self._event(run_id, "inspect_repository", "capturing repository snapshot")
        self._event(run_id, "draft_spec", "writing specification artifact")
        self._event(run_id, "create_execution_plan", "choosing execution strategy")
        self._event(run_id, "materialize_tasks", "preparing worker tasks")
        context = self._build_runtime_context(repo, run_id)
        graph_result = build_workflow_graph(context=context).compile().invoke(state)
        final_state = WorkflowState.model_validate(graph_result)
        self._store_run(final_state, run_dir)
        self.save_checkpoint(final_state)
        message = (
            "run completed"
            if final_state.status == RunStatus.READY_FOR_HUMAN_REVIEW
            else self._message_for_human_required(repo, final_state)
        )
        return RunResult(
            run_id=run_id,
            status=final_state.status,
            run_dir=run_dir.as_posix(),
            repair_attempts=final_state.repair_attempts,
            message=message,
        )

    def _build_runtime_context(
        self,
        repo: ArtifactRepository,
        run_id: str,
    ) -> WorkflowRuntimeContext:
        def review_callback(
            gate_report: ArtifactEnvelope[GateReportData],
            completed_task_ids: list[str],
            _state: WorkflowState,
        ) -> ArtifactEnvelope[ReviewReportData]:
            return self._review(repo, run_id, gate_report, completed_task_ids)

        def evidence_callback(
            goal: ArtifactEnvelope[GoalData],
            gate_report: ArtifactEnvelope[GateReportData],
            review: ArtifactEnvelope[ReviewReportData],
            strategy: ExecutionStrategy,
            completed_task_ids: list[str],
            _state: WorkflowState,
        ) -> ArtifactEnvelope[EvidenceBundleData]:
            return self._evidence(
                repo,
                run_id,
                goal,
                gate_report,
                review,
                strategy,
                completed_task_ids,
            )

        return WorkflowRuntimeContext(
            repo=repo,
            artifacts=self.artifacts,
            checkpoints=self.checkpoints,
            task_execution=self.task_execution,
            verification=self.verification,
            review_delivery=self.review_delivery,
            repair=self.repairs,
            on_dispatch=lambda task_id: self._event(
                run_id,
                "dispatch_tasks",
                f"dispatch {task_id}",
            ),
            review_callback=review_callback,
            evidence_callback=evidence_callback,
        )

    def _message_for_human_required(
        self,
        repo: ArtifactRepository,
        state: WorkflowState,
    ) -> str:
        if state.last_error == "plan validation failed":
            plan = ArtifactEnvelope[ExecutionPlanData].model_validate(
                repo.read("03_execution_plan.yaml", ArtifactType.EXECUTION_PLAN).model_dump(
                    mode="json"
                )
            )
            first_error = plan.data.validation.errors[0]
            return f"plan validation failed: {first_error}"
        return state.last_error or "evidence requires human attention"

    def save_checkpoint(self, state: WorkflowState) -> None:
        self.checkpoints.save(state, utc_now())
        self.langgraph_checkpoints.save(state)

    def langgraph_checkpointer(self) -> Any | None:
        return self.langgraph_checkpoints.checkpointer()

    def compile_langgraph(self) -> Any:
        return self.langgraph_checkpoints.compile_graph()

    def resume(self, run_id: str) -> RunResult:
        state = self._load_resume_state(run_id)
        if state is None or state.raw_goal is None:
            return RunResult(
                run_id=run_id,
                status=RunStatus.HUMAN_REQUIRED,
                run_dir=(self.runs_dir / run_id).as_posix(),
                repair_attempts=0,
                message=f"unknown run {run_id}",
            )
        run_dir = self.runs_dir / run_id
        repo = ArtifactRepository(run_dir)
        stale_errors = self._validate_resume_artifacts(repo)
        if stale_errors:
            state.status = RunStatus.HUMAN_REQUIRED
            state.current_stage = "human_required"
            state.run_dir = run_dir.as_posix()
            state.stale_artifacts = stale_errors
            state.last_error = "stale artifact lineage detected"
            self._store_run(state, run_dir)
            self.save_checkpoint(state)
            return RunResult(
                run_id=run_id,
                status=state.status,
                run_dir=run_dir.as_posix(),
                repair_attempts=state.repair_attempts,
                message=f"stale artifact lineage detected: {stale_errors[0]}",
            )
        mode = ExecutionMode(state.requested_mode)
        return self.run(state.raw_goal, mode=mode, resume_run_id=run_id)

    def _load_resume_state(self, run_id: str) -> WorkflowState | None:
        state = self._load_langgraph_checkpoint(run_id)
        return state or self.checkpoints.load(run_id)

    def _load_langgraph_checkpoint(self, run_id: str) -> WorkflowState | None:
        return self.langgraph_checkpoints.load(run_id)

    def _validate_resume_artifacts(self, repo: ArtifactRepository) -> list[str]:
        validator = ArtifactLineageValidator(repo)
        errors: list[str] = []
        for artifact_path in self._existing_artifact_paths(repo):
            try:
                artifact_errors = validator.validate_inputs(artifact_path)
            except (OSError, ValueError) as exc:
                errors.append(f"{artifact_path}: {exc}")
                continue
            errors.extend(f"{artifact_path}: {error}" for error in artifact_errors)
        return errors

    def _existing_artifact_paths(self, repo: ArtifactRepository) -> list[str]:
        paths: list[str] = []
        for path in sorted(repo.root.rglob("*.yaml")):
            relative = path.relative_to(repo.root)
            if relative.parts and relative.parts[0] == "history":
                continue
            paths.append(relative.as_posix())
        return paths

    def _backend_from_config(self) -> CodingBackend:
        return create_backend(self.config)

    def _envelope(
        self,
        *,
        run_id: str,
        artifact_type: ArtifactType,
        artifact_id_prefix: str,
        status: ArtifactStatus | str,
        producer: Producer,
        data: Any,
        inputs: list[ArtifactInput] | None = None,
    ) -> ArtifactEnvelope[Any]:
        return ArtifactEnvelope[Any](
            artifact_type=artifact_type,
            artifact_id=new_id(artifact_id_prefix),
            run_id=run_id,
            revision=1,
            status=status,
            created_at=utc_now(),
            producer=producer,
            inputs=inputs or [],
            metadata=ArtifactMetadata(),
            data=data,
        )

    def _repair(
        self,
        repo: ArtifactRepository,
        run_id: str,
        builder_handle: WorkerHandle,
        gate_report: ArtifactEnvelope[GateReportData],
        attempt: int,
        target_task_id: str,
    ) -> None:
        self.repairs.repair(
            repo,
            run_id,
            builder_handle,
            gate_report,
            attempt,
            target_task_id,
        )

    def _review(
        self,
        repo: ArtifactRepository,
        run_id: str,
        gate_report: ArtifactEnvelope[GateReportData],
        completed_task_ids: list[str],
    ) -> ArtifactEnvelope[ReviewReportData]:
        return self.review_delivery.review(repo, run_id, gate_report, completed_task_ids)

    def _evidence(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
        gate_report: ArtifactEnvelope[GateReportData],
        review: ArtifactEnvelope[ReviewReportData],
        strategy: ExecutionStrategy,
        completed_task_ids: list[str],
    ) -> ArtifactEnvelope[EvidenceBundleData]:
        return self.review_delivery.evidence(
            repo,
            run_id,
            goal,
            gate_report,
            review,
            strategy,
            completed_task_ids,
        )

    def _store_run(self, state: WorkflowState, run_dir: Path) -> None:
        self.db.upsert_run(state.run_id, state.status, run_dir.as_posix(), utc_now())

    def _event(self, run_id: str, stage: str, message: str) -> None:
        self.db.add_event(run_id, stage, message, utc_now())
        self._progress(stage, message)

    def _progress(self, stage: str, message: str) -> None:
        if self.progress is not None:
            self.progress(stage, message)
