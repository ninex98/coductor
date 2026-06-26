"""Task materialization and builder dispatch."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    FileReference,
    PlanTask,
    Producer,
    TaskData,
    WorkerRequestData,
    WorkerResultData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import CodingBackend, WorkerHandle, WorkerRequest
from coductor.config.models import CoductorConfig
from coductor.contracts.models import ContractArtifact
from coductor.contracts.repository import ContractRepository
from coductor.domain.enums import ArtifactStatus, ArtifactType, ProducerKind, SandboxMode
from coductor.prompts.renderer import render_worker_prompt
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class ExecutedTask:
    def __init__(self, task_id: str, handle: WorkerHandle) -> None:
        self.task_id = task_id
        self.handle = handle


class TaskExecutionService:
    def __init__(
        self,
        root: Path,
        config: CoductorConfig,
        backend: CodingBackend,
        artifacts: WorkflowArtifactWriter,
    ) -> None:
        self.root = root
        self.config = config
        self.backend = backend
        self.artifacts = artifacts

    def execute_plan_tasks(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        *,
        on_dispatch: Callable[[str, WorkerHandle], None],
    ) -> list[ExecutedTask]:
        executed: list[ExecutedTask] = []
        contracts: dict[str, ContractArtifact] = {}
        for plan_task in self.tasks_in_dependency_order(plan.data.tasks):
            task_contracts = [
                contract
                for path, contract in contracts.items()
                if path in plan_task.consumes
            ]
            task = self.write_task(repo, run_id, plan, plan_task, task_contracts)
            worker_handle = self.dispatch_builder(repo, run_id, task)
            on_dispatch(plan_task.id, worker_handle)
            executed.append(ExecutedTask(plan_task.id, worker_handle))
            contracts.update(self.materialize_contracts(repo, plan_task))
        return executed

    def materialize_contracts(
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

    def tasks_in_dependency_order(self, tasks: list[PlanTask]) -> list[PlanTask]:
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

    def failed_task_ids(self, repo: ArtifactRepository, task_ids: list[str]) -> list[str]:
        failed: list[str] = []
        for task_id in task_ids:
            result = repo.read(f"tasks/{task_id}/worker_result.yaml", ArtifactType.WORKER_RESULT)
            data = WorkerResultData.model_validate(result.data)
            if data.exit_reason != "completed":
                failed.append(task_id)
        return failed

    def write_task(
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
        envelope = self.artifacts.envelope(
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

    def dispatch_builder(
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
        request_envelope = self.artifacts.envelope(
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
        patch = self.ensure_patch(repo.root, task_id)
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
        result_envelope = self.artifacts.envelope(
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

    def ensure_patch(self, run_dir: Path, task_id: str) -> Path:
        patch = run_dir / f"tasks/{task_id}/patch.diff"
        patch.parent.mkdir(parents=True, exist_ok=True)
        if not patch.exists():
            patch.write_text("# fake backend did not produce a patch\n", encoding="utf-8")
        return patch
