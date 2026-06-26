"""Phase 1 vertical workflow service."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    ArtifactMetadata,
    EvidenceBundleData,
    FileReference,
    GateReportData,
    GoalData,
    PlanTask,
    Producer,
    RepairRequestData,
    RepositorySnapshotData,
    ReviewReportData,
    SpecificationData,
    TaskData,
    WorkerRequestData,
    WorkerResultData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.validator import ArtifactLineageValidator
from coductor.backends.base import CodingBackend, WorkerHandle, WorkerRequest
from coductor.backends.factory import create_backend
from coductor.config.models import CoductorConfig
from coductor.contracts.models import ContractArtifact
from coductor.contracts.repository import ContractRepository
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ExecutionStrategy,
    ProducerKind,
    RunStatus,
    SandboxMode,
)
from coductor.domain.ids import new_id
from coductor.domain.models import RunResult
from coductor.gates.models import QualityGate
from coductor.gates.runner import GateRunner
from coductor.prompts.renderer import render_worker_prompt
from coductor.repository.merge import build_integration_data
from coductor.services.evidence_service import EvidenceService
from coductor.storage.database import Database
from coductor.workflow.artifact_writer import WorkflowArtifactWriter
from coductor.workflow.checkpoint import WorkflowCheckpointStore
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
        self.save_checkpoint(state)
        self._event(run_id, "collect_goal", "accepted user goal")

        goal = self._write_goal(repo, run_id, raw_goal, requested_mode)
        state.artifacts["00_goal"] = "00_goal.yaml"
        state.current_stage = "inspect_repository"
        self.save_checkpoint(state)
        self._event(run_id, "inspect_repository", "capturing repository snapshot")
        snapshot = self._write_snapshot(repo, run_id, goal)
        state.artifacts["01_repository_snapshot"] = "01_repository_snapshot.yaml"
        state.current_stage = "draft_spec"
        self.save_checkpoint(state)
        self._event(run_id, "draft_spec", "writing specification artifact")
        spec = self._write_spec(repo, run_id, goal, snapshot)
        state.artifacts["02_spec"] = "02_spec.yaml"
        state.current_stage = "create_execution_plan"
        self.save_checkpoint(state)
        self._event(run_id, "create_execution_plan", "choosing execution strategy")
        plan = self._write_plan(repo, run_id, spec, snapshot, requested_mode)
        state.artifacts["03_execution_plan"] = "03_execution_plan.yaml"
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
        executed_tasks = self._execute_plan_tasks(repo, run_id, plan, state)
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
        failed_task_ids = self._failed_task_ids(
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
        self._write_integration(repo, run_id, plan, completed_task_ids)
        state.artifacts["04_integration"] = "04_integration.yaml"
        state.current_stage = "run_quality_gates"
        self.save_checkpoint(state)
        self._event(run_id, "run_quality_gates", "running configured quality gates")

        gate_report: ArtifactEnvelope[GateReportData] | None = None
        last_fingerprint: str | None = None
        repeated_fingerprints = 0
        while True:
            gate_report = self._run_gates(repo, run_id)
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

        review = self._review(repo, run_id, gate_report, completed_task_ids)
        state.artifacts["06_review"] = "06_review.yaml"
        state.current_stage = "run_independent_review"
        self.save_checkpoint(state)
        self._event(run_id, "run_independent_review", "reviewing worker result")
        evidence = self._evidence(
            repo,
            run_id,
            goal,
            gate_report,
            review,
            plan.data.strategy,
            completed_task_ids,
        )
        state.artifacts["07_evidence"] = "07_evidence.yaml"
        self._event(run_id, "prepare_evidence", "writing evidence bundle")
        state.status = (
            RunStatus.READY_FOR_HUMAN_REVIEW
            if evidence.data.final_status == "ready_for_human_review"
            else RunStatus.HUMAN_REQUIRED
        )
        state.current_stage = "prepare_evidence"
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

    def _write_goal(
        self,
        repo: ArtifactRepository,
        run_id: str,
        raw_goal: str,
        requested_mode: ExecutionMode,
    ) -> ArtifactEnvelope[GoalData]:
        return self.artifacts.write_goal(repo, run_id, raw_goal, requested_mode)

    def _write_snapshot(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
    ) -> ArtifactEnvelope[RepositorySnapshotData]:
        return self.artifacts.write_snapshot(repo, run_id, goal)

    def _write_spec(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
        snapshot: ArtifactEnvelope[RepositorySnapshotData],
    ) -> ArtifactEnvelope[SpecificationData]:
        return self.artifacts.write_spec(repo, run_id, goal, snapshot)

    def _write_plan(
        self,
        repo: ArtifactRepository,
        run_id: str,
        spec: ArtifactEnvelope[SpecificationData],
        snapshot: ArtifactEnvelope[RepositorySnapshotData],
        requested_mode: ExecutionMode,
    ) -> ArtifactEnvelope[Any]:
        return self.artifacts.write_plan(repo, run_id, spec, snapshot, requested_mode)

    def _execute_plan_tasks(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        state: WorkflowState,
    ) -> list[tuple[str, WorkerHandle]]:
        executed: list[tuple[str, WorkerHandle]] = []
        contracts: dict[str, ContractArtifact] = {}
        for plan_task in self._tasks_in_dependency_order(plan.data.tasks):
            task_contracts = [
                contract
                for path, contract in contracts.items()
                if path in plan_task.consumes
            ]
            task = self._write_task(repo, run_id, plan, plan_task, task_contracts)
            task_path = f"tasks/{plan_task.id}/task.yaml"
            state.artifacts[f"task_{plan_task.id}"] = task_path
            state.current_stage = "dispatch_tasks"
            self.save_checkpoint(state)
            self._event(run_id, "dispatch_tasks", f"dispatch {plan_task.id}")
            worker_handle = self._dispatch_builder(repo, run_id, task)
            state.artifacts[f"worker_result_{plan_task.id}"] = (
                f"tasks/{plan_task.id}/worker_result.yaml"
            )
            self.save_checkpoint(state)
            executed.append((plan_task.id, worker_handle))
            contracts.update(self._materialize_contracts(repo, plan_task))
        return executed

    def _materialize_contracts(
        self,
        repo: ArtifactRepository,
        plan_task: PlanTask,
    ) -> dict[str, ContractArtifact]:
        materialized: dict[str, ContractArtifact] = {}
        for produced in plan_task.produces:
            if not produced.startswith("contracts/"):
                continue
            path = repo.root / produced
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text('{"type":"object"}\n', encoding="utf-8")
            contract = ContractRepository(repo.root).record(
                produced,
                kind="json_schema",
                producer_task_id=plan_task.id,
            )
            materialized[produced] = contract
        return materialized

    def _tasks_in_dependency_order(self, tasks: list[PlanTask]) -> list[PlanTask]:
        remaining = {task.id: task for task in tasks}
        completed: set[str] = set()
        ordered: list[PlanTask] = []
        while remaining:
            ready = [
                task
                for task in remaining.values()
                if all(dependency in completed for dependency in task.depends_on)
            ]
            if not ready:
                return tasks
            ready.sort(key=lambda task: task.id)
            task = ready[0]
            ordered.append(task)
            completed.add(task.id)
            del remaining[task.id]
        return ordered

    def _failed_task_ids(self, repo: ArtifactRepository, task_ids: list[str]) -> list[str]:
        failed: list[str] = []
        for task_id in task_ids:
            result = repo.read(f"tasks/{task_id}/worker_result.yaml", ArtifactType.WORKER_RESULT)
            data = WorkerResultData.model_validate(result.data)
            if data.exit_reason != "completed":
                failed.append(task_id)
        return failed

    def _write_task(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        plan_task: PlanTask,
        contracts: list[ContractArtifact],
    ) -> ArtifactEnvelope[TaskData]:
        data = TaskData(
            task_id=plan_task.id,
            objective=plan_task.title,
            role=plan_task.role,
            depends_on=plan_task.depends_on,
            global_context=["00_goal.yaml", "01_repository_snapshot.yaml", "02_spec.yaml"],
            upstream_artifacts=[
                f"tasks/{dependency}/worker_result.yaml"
                for dependency in plan_task.depends_on
            ],
            allowed_paths=plan_task.allowed_paths,
            forbidden_paths=plan_task.forbidden_paths,
            expected_outputs=plan_task.produces,
            contracts=contracts,
            acceptance_criteria=plan_task.acceptance_criteria,
            quality_gates=plan_task.quality_gates,
        )
        envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.TASK,
            artifact_id_prefix="art_task",
            status=ArtifactStatus.READY,
            producer=Producer(kind=ProducerKind.SYSTEM, name="task-materializer"),
            inputs=[ArtifactInput.model_validate(repo.input_for("03_execution_plan.yaml", plan))],
            data=data,
        )
        repo.write(f"tasks/{plan_task.id}/task.yaml", envelope)
        return envelope

    def _dispatch_builder(
        self,
        repo: ArtifactRepository,
        run_id: str,
        task: ArtifactEnvelope[TaskData],
    ) -> WorkerHandle:
        task_id = task.data.task_id
        task_path = f"tasks/{task_id}/task.yaml"
        request_data = WorkerRequestData(
            worker_id=f"worker_{task_id}",
            backend=self.config.backend.provider,
            role="builder",
            sandbox=SandboxMode.WORKSPACE_WRITE,
            workspace_path=".",
            prompt_template="builder",
            context_artifacts=task.data.global_context
            + task.data.upstream_artifacts
            + [task_path],
            output_schema="worker_result",
        )
        request_envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.WORKER_REQUEST,
            artifact_id_prefix="art_worker_req",
            status=ArtifactStatus.READY,
            producer=Producer(kind=ProducerKind.SYSTEM, name="worker-dispatcher"),
            data=request_data,
            inputs=[ArtifactInput.model_validate(repo.input_for(task_path, task))],
        )
        repo.write(f"tasks/{task_id}/worker_request.yaml", request_envelope)
        prompt = render_worker_prompt(
            "builder",
            request_data.context_artifacts,
            task.data.objective,
        )
        request = WorkerRequest(
            worker_id=request_data.worker_id,
            role="builder",
            prompt=prompt,
            workspace_path=self.root.as_posix(),
            sandbox=SandboxMode.WORKSPACE_WRITE,
        )
        handle = self.backend.start_worker(request)
        result = self.backend.continue_worker(handle, request)
        patch = self._ensure_patch(repo.root, task_id)
        result_data = WorkerResultData(
            worker_id=result.worker_id,
            thread_id=result.thread_id,
            task_id=task_id,
            summary=result.summary,
            files_read=result.files_read,
            files_changed=result.files_changed,
            commands_run=result.commands_run,
            tests_claimed=result.tests_claimed,
            generated_artifacts=result.generated_artifacts,
            patch=FileReference(
                path=f"tasks/{task_id}/patch.diff",
                sha256=file_sha256(patch),
                bytes=patch.stat().st_size,
            ),
            unresolved_issues=result.unresolved_issues,
            exit_reason=result.exit_reason,
        )
        result_envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.WORKER_RESULT,
            artifact_id_prefix="art_worker_result",
            status=ArtifactStatus.COMPLETED,
            producer=Producer(kind=ProducerKind.MODEL, name="codex-worker"),
            data=result_data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for(f"tasks/{task_id}/worker_request.yaml", request_envelope)
                )
            ],
        )
        repo.write(f"tasks/{task_id}/worker_result.yaml", result_envelope)
        return handle

    def _ensure_patch(self, run_dir: Path, task_id: str) -> Path:
        patch = run_dir / f"tasks/{task_id}/patch.diff"
        patch.parent.mkdir(parents=True, exist_ok=True)
        if not patch.exists():
            patch.write_text("# fake backend did not produce a patch\n", encoding="utf-8")
        return patch

    def _write_integration(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        completed_task_ids: list[str],
    ) -> None:
        data = build_integration_data(plan.data.strategy, completed_task_ids)
        envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.INTEGRATION,
            artifact_id_prefix="art_integration",
            status=(
                ArtifactStatus.SKIPPED
                if data.status == "skipped"
                else ArtifactStatus.COMPLETE
            ),
            producer=Producer(kind=ProducerKind.SYSTEM, name="integration-manager"),
            data=data,
            inputs=[ArtifactInput.model_validate(repo.input_for("03_execution_plan.yaml", plan))],
        )
        repo.write("04_integration.yaml", envelope)

    def _run_gates(self, repo: ArtifactRepository, run_id: str) -> ArtifactEnvelope[GateReportData]:
        gates = [
            QualityGate(
                id=gate.id,
                stage=gate.stage,
                command=gate.command,
                required=gate.required,
                timeout_seconds=gate.timeout_seconds,
            )
            for gate in self.config.quality_gates
        ]
        data = GateRunner(self.root, run_dir=repo.root).run(gates)
        status = ArtifactStatus.PASSED if data.required_gates_passed else ArtifactStatus.FAILED
        envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.GATE_REPORT,
            artifact_id_prefix="art_gates",
            status=status,
            producer=Producer(kind=ProducerKind.TOOL, name="gate-runner"),
            data=data,
        )
        repo.write("05_gate_report.yaml", envelope)
        return envelope

    def _repair(
        self,
        repo: ArtifactRepository,
        run_id: str,
        builder_handle: WorkerHandle,
        gate_report: ArtifactEnvelope[GateReportData],
        attempt: int,
        target_task_id: str,
    ) -> None:
        failed = [gate.id for gate in gate_report.data.gates if gate.status != "passed"]
        fingerprints = [
            gate.failure_fingerprint for gate in gate_report.data.gates if gate.failure_fingerprint
        ]
        repair_id = f"R{attempt:03d}"
        repair_dir = f"repairs/{repair_id}"
        request_data = RepairRequestData(
            repair_id=repair_id,
            target_task_id=target_task_id,
            resume_thread_id=builder_handle.thread_id,
            attempt=attempt,
            max_attempts=self.config.workflow.max_repair_attempts,
            failed_gates=failed,
            failure_fingerprints=[fp for fp in fingerprints if fp],
            evidence_paths=["05_gate_report.yaml"],
            allowed_paths=["src/**", "tests/**"],
        )
        request_envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPAIR_REQUEST,
            artifact_id_prefix="art_repair_req",
            status=ArtifactStatus.READY,
            producer=Producer(kind=ProducerKind.SYSTEM, name="repair-planner"),
            data=request_data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for("05_gate_report.yaml", gate_report)
                )
            ],
        )
        repo.write(f"{repair_dir}/repair_request.yaml", request_envelope)
        request = WorkerRequest(
            worker_id=f"worker_{target_task_id}_repair",
            role="repairer",
            prompt=render_worker_prompt(
                "repairer",
                ["05_gate_report.yaml"],
                request_data.instruction,
            ),
            workspace_path=self.root.as_posix(),
            sandbox=SandboxMode.WORKSPACE_WRITE,
            thread_policy="resume",
            existing_thread_id=builder_handle.thread_id,
        )
        result = self.backend.continue_worker(builder_handle, request)
        patch = repo.root / f"{repair_dir}/repair_result.patch"
        patch.write_text("# fake repair result\n", encoding="utf-8")
        result_data = WorkerResultData(
            worker_id=result.worker_id,
            thread_id=result.thread_id,
            task_id=target_task_id,
            summary=result.summary,
            patch=FileReference(
                path=f"{repair_dir}/repair_result.patch",
                sha256=file_sha256(patch),
                bytes=patch.stat().st_size,
            ),
            exit_reason=result.exit_reason,
        )
        result_envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPAIR_RESULT,
            artifact_id_prefix="art_repair_result",
            status=ArtifactStatus.COMPLETED,
            producer=Producer(kind=ProducerKind.MODEL, name="repair-worker"),
            data=result_data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for(f"{repair_dir}/repair_request.yaml", request_envelope)
                )
            ],
        )
        repo.write(f"{repair_dir}/repair_result.yaml", result_envelope)

    def _review(
        self,
        repo: ArtifactRepository,
        run_id: str,
        gate_report: ArtifactEnvelope[GateReportData],
        completed_task_ids: list[str],
    ) -> ArtifactEnvelope[ReviewReportData]:
        patch_paths = [
            f"tasks/{task_id}/patch.diff"
            for task_id in completed_task_ids
            if (repo.root / f"tasks/{task_id}/patch.diff").exists()
        ]
        request = WorkerRequest(
            worker_id="worker_review",
            role="reviewer",
            prompt=render_worker_prompt(
                "reviewer",
                ["02_spec.yaml", "05_gate_report.yaml", *patch_paths],
                "independently review the verified change",
            ),
            workspace_path=self.root.as_posix(),
            sandbox=SandboxMode.READ_ONLY,
        )
        handle = self.backend.start_worker(request)
        result = self.backend.continue_worker(handle, request)
        data = ReviewReportData(
            reviewer_thread_id=result.thread_id,
            reviewed_base_commit=gate_report.data.base_commit,
            reviewed_head_commit=gate_report.data.head_commit,
            findings=[],
            blocking_findings=0,
            verdict="pass",
            requires_repair=False,
        )
        envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REVIEW_REPORT,
            artifact_id_prefix="art_review",
            status=ArtifactStatus.PASSED,
            producer=Producer(kind=ProducerKind.MODEL, name="independent-reviewer"),
            data=data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for("05_gate_report.yaml", gate_report)
                )
            ],
        )
        repo.write("06_review.yaml", envelope)
        return envelope

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
        service = EvidenceService()
        data = service.build(
            run_dir=repo.root,
            goal_title=goal.data.title,
            strategy=strategy,
            gate_report=gate_report.data,
            review=review.data,
            completed_tasks=completed_task_ids,
        )
        envelope = self._envelope(
            run_id=run_id,
            artifact_type=ArtifactType.EVIDENCE_BUNDLE,
            artifact_id_prefix="art_evidence",
            status=(
                ArtifactStatus.READY_FOR_HUMAN_REVIEW
                if data.final_status == "ready_for_human_review"
                else ArtifactStatus.HUMAN_REQUIRED
            ),
            producer=Producer(kind=ProducerKind.SYSTEM, name="delivery-manager"),
            data=data,
            inputs=[
                ArtifactInput.model_validate(repo.input_for("05_gate_report.yaml", gate_report)),
                ArtifactInput.model_validate(repo.input_for("06_review.yaml", review)),
            ],
        )
        repo.write("07_evidence.yaml", envelope)
        service.write_report(repo.root, data)
        return envelope

    def _store_run(self, state: WorkflowState, run_dir: Path) -> None:
        self.db.upsert_run(state.run_id, state.status, run_dir.as_posix(), utc_now())

    def _event(self, run_id: str, stage: str, message: str) -> None:
        self.db.add_event(run_id, stage, message, utc_now())
        self._progress(stage, message)

    def _progress(self, stage: str, message: str) -> None:
        if self.progress is not None:
            self.progress(stage, message)
