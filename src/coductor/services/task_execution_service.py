"""Task materialization and builder dispatch."""

from __future__ import annotations

import difflib
import fnmatch
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionStrategy,
    ProducerKind,
    SandboxMode,
)
from coductor.prompts.renderer import render_worker_prompt
from coductor.repository.worktree import WorktreeManager
from coductor.services.usage import usage_from_backend
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class ExecutedTask:
    def __init__(
        self,
        task_id: str,
        handle: WorkerHandle,
        *,
        produced_contracts: dict[str, ContractArtifact] | None = None,
    ) -> None:
        self.task_id = task_id
        self.handle = handle
        self.produced_contracts = produced_contracts or {}


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
        self.worktrees = WorktreeManager(root)

    def execute_plan_tasks(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        *,
        on_dispatch: Callable[[str, WorkerHandle], None],
    ) -> list[ExecutedTask]:
        if str(plan.data.strategy) == ExecutionStrategy.PARALLEL:
            return self.execute_parallel_plan_tasks(repo, run_id, plan, on_dispatch=on_dispatch)
        executed: list[ExecutedTask] = []
        contracts: dict[str, ContractArtifact] = {}
        for plan_task in self.tasks_in_dependency_order(plan.data.tasks):
            executed_task = self.execute_plan_task(
                repo,
                run_id,
                plan,
                plan_task,
                contracts,
                on_dispatch=on_dispatch,
            )
            executed.append(executed_task)
            contracts.update(executed_task.produced_contracts)
        return executed

    def execute_parallel_plan_tasks(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        *,
        on_dispatch: Callable[[str, WorkerHandle], None],
    ) -> list[ExecutedTask]:
        executed: list[ExecutedTask] = []
        completed: set[str] = set()
        remaining = {task.id: task for task in plan.data.tasks}
        max_workers = max(1, self.config.workflow.max_parallel_workers)
        while remaining:
            ready = [
                task
                for task in remaining.values()
                if all(dependency in completed for dependency in task.depends_on)
            ]
            if not ready:
                return self.execute_plan_tasks_sequentially(
                    repo,
                    run_id,
                    plan,
                    on_dispatch=on_dispatch,
                    skip_task_ids=completed,
                )
            ready.sort(key=lambda task: task.id)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self.execute_plan_task,
                        repo,
                        run_id,
                        plan,
                        task,
                        {},
                        on_dispatch=lambda *_: None,
                    ): task
                    for task in ready
                }
                batch: list[ExecutedTask] = []
                for future in as_completed(futures):
                    batch.append(future.result())
            self.apply_parallel_patches(repo, plan.data.strategy, batch)
            batch.sort(key=lambda task: task.task_id)
            for executed_task in batch:
                on_dispatch(executed_task.task_id, executed_task.handle)
                executed.append(executed_task)
                completed.add(executed_task.task_id)
                remaining.pop(executed_task.task_id, None)
        return executed

    def execute_plan_tasks_sequentially(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        *,
        on_dispatch: Callable[[str, WorkerHandle], None],
        skip_task_ids: set[str] | None = None,
    ) -> list[ExecutedTask]:
        executed: list[ExecutedTask] = []
        contracts: dict[str, ContractArtifact] = {}
        skip_task_ids = skip_task_ids or set()
        for plan_task in self.tasks_in_dependency_order(plan.data.tasks):
            if plan_task.id in skip_task_ids:
                continue
            executed_task = self.execute_plan_task(
                repo,
                run_id,
                plan,
                plan_task,
                contracts,
                on_dispatch=on_dispatch,
            )
            executed.append(executed_task)
            contracts.update(executed_task.produced_contracts)
        return executed

    def execute_plan_task(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        plan_task: PlanTask,
        contracts: dict[str, ContractArtifact],
        *,
        on_dispatch: Callable[[str, WorkerHandle], None],
    ) -> ExecutedTask:
        task_contracts = [
            contract
            for path, contract in contracts.items()
            if path in plan_task.consumes
        ]
        task = self.write_task(repo, run_id, plan, plan_task, task_contracts)
        worker_handle = self.dispatch_builder(
            repo,
            run_id,
            task,
            strategy=plan.data.strategy,
            base_commit=plan.data.base_commit,
        )
        on_dispatch(plan_task.id, worker_handle)
        return ExecutedTask(
            plan_task.id,
            worker_handle,
            produced_contracts=self.materialize_contracts(repo, plan_task),
        )

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
        *,
        strategy: ExecutionStrategy,
        base_commit: str,
    ) -> WorkerHandle:
        task_id = task.data.task_id
        task_path = f"tasks/{task_id}/task.yaml"
        workspace = self._worker_workspace(run_id, task_id, strategy, base_commit)
        request_data = WorkerRequestData(
            worker_id=f"worker_{task_id}",
            backend=self.config.backend.provider,
            role="builder",
            sandbox=SandboxMode.WORKSPACE_WRITE,
            workspace_path=workspace.relative_to(self.root).as_posix()
            if workspace.is_relative_to(self.root)
            else workspace.as_posix(),
            prompt_template="builder",
            context_artifacts=task.data.global_context
            + task.data.upstream_artifacts
            + [task_path],
            output_schema="worker_result",
            timeout_seconds=self.config.budgets.max_run_minutes * 60,
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
        try:
            prompt = render_worker_prompt(
                "builder",
                request_data.context_artifacts,
                task.data.objective,
            )
            before_snapshot = self.workspace_snapshot(workspace)
            request = WorkerRequest(
                worker_id=request_data.worker_id,
                role="builder",
                prompt=prompt,
                workspace_path=workspace.as_posix(),
                sandbox=SandboxMode.WORKSPACE_WRITE,
                timeout_seconds=request_data.timeout_seconds,
            )
            started_at = time.monotonic()
            handle = self.backend.start_worker(request)
            result = self.backend.continue_worker(handle, request)
            duration_ms = int((time.monotonic() - started_at) * 1000)
            patch = self.ensure_patch(
                repo.root,
                task_id,
                workspace=workspace,
                before_snapshot=before_snapshot,
            )
            apply_issues: list[str] = []
            protected_issues = self.protected_path_issues(result.files_changed, patch)
            exit_reason = "failed" if protected_issues or apply_issues else result.exit_reason
            unresolved_issues = result.unresolved_issues + apply_issues + protected_issues
        finally:
            self._cleanup_worker_workspace(run_id, task_id, strategy)
        usage = usage_from_backend(
            result.usage,
            prompt=prompt,
            summary=result.summary,
            duration_ms=duration_ms,
        )
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
            unresolved_issues=unresolved_issues,
            usage=usage,
            exit_reason=exit_reason,
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

    def apply_parallel_patches(
        self,
        repo: ArtifactRepository,
        strategy: ExecutionStrategy,
        executed_tasks: list[ExecutedTask],
    ) -> None:
        if str(strategy) != ExecutionStrategy.PARALLEL or not self.worktrees.is_available():
            return
        for executed_task in sorted(executed_tasks, key=lambda task: task.task_id):
            patch = repo.root / f"tasks/{executed_task.task_id}/patch.diff"
            issues = self._apply_parallel_patch(patch)
            if issues:
                self.mark_worker_result_failed(repo, executed_task.task_id, issues)

    def mark_worker_result_failed(
        self,
        repo: ArtifactRepository,
        task_id: str,
        issues: list[str],
    ) -> None:
        relative_path = f"tasks/{task_id}/worker_result.yaml"
        envelope = repo.read(relative_path, ArtifactType.WORKER_RESULT)
        data = WorkerResultData.model_validate(envelope.data)
        data.unresolved_issues.extend(issues)
        data.exit_reason = "failed"
        envelope.data = data
        repo.write_next_revision(relative_path, envelope)

    def _worker_workspace(
        self,
        run_id: str,
        task_id: str,
        strategy: ExecutionStrategy,
        base_commit: str,
    ) -> Path:
        if str(strategy) != ExecutionStrategy.PARALLEL or not self.worktrees.is_available():
            return self.root
        return self.worktrees.create(run_id, task_id, base_commit)

    def _cleanup_worker_workspace(
        self,
        run_id: str,
        task_id: str,
        strategy: ExecutionStrategy,
    ) -> None:
        if str(strategy) != ExecutionStrategy.PARALLEL or not self.worktrees.is_available():
            return
        self.worktrees.remove(run_id, task_id)

    def _apply_parallel_patch(self, patch: Path) -> list[str]:
        if not _patch_has_changes(patch):
            return []
        result = self.worktrees.apply(patch)
        if result.returncode == 0:
            return []
        message = result.stderr.strip() or result.stdout.strip() or "git apply failed"
        return [f"parallel patch apply failed: {message}"]

    def ensure_patch(
        self,
        run_dir: Path,
        task_id: str,
        *,
        workspace: Path | None = None,
        before_snapshot: dict[str, str] | None = None,
    ) -> Path:
        patch = run_dir / f"tasks/{task_id}/patch.diff"
        patch.parent.mkdir(parents=True, exist_ok=True)
        workspace = workspace or self.root
        diff = self.workspace_diff(workspace)
        if not diff.strip() and before_snapshot is not None:
            diff = self.snapshot_diff(before_snapshot, self.workspace_snapshot(workspace))
        if diff.strip():
            patch.write_text(diff, encoding="utf-8")
        else:
            patch.write_text("# coductor no workspace diff captured\n", encoding="utf-8")
        return patch

    def workspace_snapshot(self, workspace: Path | None = None) -> dict[str, str]:
        workspace = workspace or self.root
        snapshot: dict[str, str] = {}
        for path in sorted(workspace.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(workspace).as_posix()
            if self._is_tool_path(relative):
                continue
            try:
                snapshot[relative] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                snapshot[relative] = "<binary>"
        return snapshot

    def snapshot_diff(self, before: dict[str, str], after: dict[str, str]) -> str:
        chunks: list[str] = []
        for relative in sorted(set(before) | set(after)):
            before_text = before.get(relative)
            after_text = after.get(relative)
            if before_text == after_text:
                continue
            if before_text == "<binary>" or after_text == "<binary>":
                chunks.append(
                    "\n".join(
                        [
                            f"diff --git a/{relative} b/{relative}",
                            "Binary files differ",
                            "",
                        ]
                    )
                )
                continue
            before_lines = [] if before_text is None else before_text.splitlines(keepends=True)
            after_lines = [] if after_text is None else after_text.splitlines(keepends=True)
            diff_lines = difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
            unified = "".join(diff_lines)
            if unified:
                chunks.append(f"diff --git a/{relative} b/{relative}\n{unified}")
        return "\n".join(chunks)

    def workspace_diff(self, workspace: Path | None = None) -> str:
        workspace = workspace or self.root
        tracked = subprocess.run(
            ["git", "diff", "--binary"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if tracked.returncode != 0:
            return ""
        chunks = [tracked.stdout]
        chunks.extend(self._untracked_file_diffs(workspace))
        return "\n".join(chunk for chunk in chunks if chunk)

    def _untracked_file_diffs(self, workspace: Path) -> list[str]:
        listed = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0:
            return []
        diffs: list[str] = []
        for relative in sorted(line for line in listed.stdout.splitlines() if line.strip()):
            if self._is_tool_path(relative):
                continue
            path = workspace / relative
            if not path.is_file():
                continue
            diff = subprocess.run(
                ["git", "diff", "--binary", "--no-index", "--", "/dev/null", relative],
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
            )
            output = diff.stdout.strip()
            if output:
                diffs.append(output + "\n")
        return diffs

    def _is_tool_path(self, relative_path: str) -> bool:
        ignored_prefixes = (
            ".coductor/",
            ".git/",
            ".venv/",
            "node_modules/",
            "vendor/",
            "__pycache__/",
        )
        return relative_path.startswith(ignored_prefixes)

    def protected_path_issues(self, files_changed: list[str], patch: Path) -> list[str]:
        changed = set(files_changed)
        changed.update(self._paths_from_patch(patch))
        issues: list[str] = []
        for path in sorted(changed):
            if self._is_protected_path(path):
                issues.append(f"protected path changed: {path}")
        return issues

    def _paths_from_patch(self, patch: Path) -> set[str]:
        paths: set[str] = set()
        if not patch.exists():
            return paths
        for line in patch.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.startswith("diff --git "):
                continue
            parts = line.split()
            if len(parts) >= 4:
                paths.add(parts[3].removeprefix("b/"))
        return paths

    def _is_protected_path(self, relative_path: str) -> bool:
        return any(
            fnmatch.fnmatch(relative_path, pattern)
            or fnmatch.fnmatch("/" + relative_path, pattern)
            for pattern in self.config.permissions.protected_paths
        )


def _patch_has_changes(path: Path) -> bool:
    content = path.read_text(encoding="utf-8", errors="replace")
    return (
        "diff --git " in content
        or "\n--- " in content
        or content.startswith("--- ")
        or "GIT binary patch" in content
    )
