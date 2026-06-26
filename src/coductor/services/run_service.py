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
from coductor.workflow.graph_runner import WorkflowGraphRunner
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
        )
        runner = WorkflowGraphRunner(
            repo=repo,
            artifacts=self.artifacts,
            checkpoints=self.checkpoints,
        )
        self.save_checkpoint(state)
        self._event(run_id, "collect_goal", "accepted user goal")

        self._event(run_id, "inspect_repository", "capturing repository snapshot")
        self._event(run_id, "draft_spec", "writing specification artifact")
        self._event(run_id, "create_execution_plan", "choosing execution strategy")
        goal, _snapshot, _spec, plan, state = runner.run_front_half(
            state,
            requested_mode=requested_mode,
        )
        if not plan.data.validation.valid:
            state.status = RunStatus.HUMAN_REQUIRED
            state.current_stage = "human_required"
            state.last_error = "plan validation failed"
            self._store_run(state, run_dir)
            self.save_checkpoint(state)
            first_error = plan.data.validation.errors[0]
            return RunResult(
                run_id=run_id,
                status=state.status,
                run_dir=run_dir.as_posix(),
                repair_attempts=state.repair_attempts,
                message=f"plan validation failed: {first_error}",
            )
        state.current_stage = "materialize_tasks"
        self.save_checkpoint(state)
        self._event(run_id, "materialize_tasks", "preparing worker tasks")
        executed, state = runner.run_task_execution(
            state,
            plan=plan,
            tasks=self.task_execution,
            on_dispatch=lambda task_id, _handle: self._event(
                run_id,
                "dispatch_tasks",
                f"dispatch {task_id}",
            ),
        )
        executed_tasks = [(item.task_id, item.handle) for item in executed]
        if not executed_tasks:
            state.status = RunStatus.HUMAN_REQUIRED
            state.current_stage = "human_required"
            self._store_run(state, run_dir)
            self.save_checkpoint(state)
            return RunResult(
                run_id=run_id,
                status=state.status,
                run_dir=run_dir.as_posix(),
                repair_attempts=state.repair_attempts,
                message="执行计划没有可运行任务",
            )
        failed_task_ids = self.task_execution.failed_task_ids(
            repo,
            [task_id for task_id, _handle in executed_tasks],
        )
        if failed_task_ids:
            state.status = RunStatus.HUMAN_REQUIRED
            state.current_stage = "human_required"
            state.last_error = f"worker failed: {', '.join(failed_task_ids)}"
            self._store_run(state, run_dir)
            self.save_checkpoint(state)
            return RunResult(
                run_id=run_id,
                status=state.status,
                run_dir=run_dir.as_posix(),
                repair_attempts=state.repair_attempts,
                message=state.last_error,
            )
        worker_handle = executed_tasks[-1][1]
        repair_target_task_id = executed_tasks[-1][0]
        completed_task_ids = [task_id for task_id, _handle in executed_tasks]
        state.current_stage = "integrate_changes"
        self.save_checkpoint(state)
        self._event(run_id, "integrate_changes", "recording integration artifact")
        state = runner.run_integration(
            state,
            plan=plan,
            completed_task_ids=completed_task_ids,
            verification=self.verification,
        )
        self._event(run_id, "run_quality_gates", "running configured quality gates")

        gate_report: ArtifactEnvelope[GateReportData] | None = None
        last_fingerprint: str | None = None
        repeated_fingerprints = 0
        while True:
            gate_report, state = runner.run_quality_gates(
                state,
                verification=self.verification,
            )
            if gate_report.data.required_gates_passed:
                break
            fingerprints = [
                gate.failure_fingerprint
                for gate in gate_report.data.gates
                if gate.failure_fingerprint
            ]
            current_fingerprint = fingerprints[0] if fingerprints else None
            repeated_fingerprints = (
                repeated_fingerprints + 1 if current_fingerprint == last_fingerprint else 1
            )
            last_fingerprint = current_fingerprint
            if (
                state.repair_attempts >= self.config.workflow.max_repair_attempts
                or repeated_fingerprints >= 2
            ):
                gate_report.data.next_action = "human_required"
                repo.write("05_gate_report.yaml", gate_report)
                state.status = RunStatus.HUMAN_REQUIRED
                state.current_stage = "human_required"
                self._store_run(state, run_dir)
                self.save_checkpoint(state)
                return RunResult(
                    run_id=run_id,
                    status=state.status,
                    run_dir=run_dir.as_posix(),
                    repair_attempts=state.repair_attempts,
                    message="质量门失败且达到停止规则",
                )
            state.repair_attempts += 1
            state.current_stage = "repair_failure"
            self.save_checkpoint(state)
            self._event(run_id, "repair_failure", f"repair attempt {state.repair_attempts}")
            self._repair(
                repo,
                run_id,
                worker_handle,
                gate_report,
                state.repair_attempts,
                repair_target_task_id,
            )
            state.current_stage = "run_quality_gates"
            self.save_checkpoint(state)

        self._event(run_id, "run_independent_review", "reviewing worker result")
        review, state = runner.run_review(
            state,
            review=lambda: self._review(repo, run_id, gate_report, completed_task_ids),
        )
        self._event(run_id, "prepare_evidence", "writing evidence bundle")
        _evidence, state = runner.run_evidence(
            state,
            evidence=lambda: self._evidence(
                repo,
                run_id,
                goal,
                gate_report,
                review,
                plan.data.strategy,
                completed_task_ids,
            ),
        )
        self._store_run(state, run_dir)
        self.save_checkpoint(state)
        message = (
            "run completed"
            if state.status == RunStatus.READY_FOR_HUMAN_REVIEW
            else "evidence requires human attention"
        )
        return RunResult(
            run_id=run_id,
            status=state.status,
            run_dir=run_dir.as_posix(),
            repair_attempts=state.repair_attempts,
            message=message,
        )

    def save_checkpoint(self, state: WorkflowState) -> None:
        self.checkpoints.save(state, utc_now())

    def resume(self, run_id: str) -> RunResult:
        state = self.checkpoints.load(run_id)
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
