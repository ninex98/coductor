from __future__ import annotations

from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import load_yaml
from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ExecutionMode
from coductor.services.task_execution_service import TaskExecutionService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class FileChangingBackend(FakeCodingBackend):
    def __init__(self, root_file) -> None:
        super().__init__()
        self.root_file = root_file

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        self.root_file.write_text("changed\n", encoding="utf-8")
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="changed tracked file",
            files_changed=[self.root_file.name],
        )


class EnvChangingBackend(FakeCodingBackend):
    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        env_path = request.workspace_path + "/.env"
        from pathlib import Path

        Path(env_path).write_text("SECRET=changed\n", encoding="utf-8")
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="changed protected file",
            files_changed=[".env"],
        )


def test_task_execution_service_dispatches_pipeline_tasks_with_contracts(tmp_path):
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    goal = writer.write_goal(repo, "run_abc", "先定义 schema 再实现功能", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)
    service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)

    executed = service.execute_plan_tasks(repo, "run_abc", plan, on_dispatch=lambda *_: None)

    assert [item.task_id for item in executed] == ["T001", "T002"]
    assert (tmp_path / "tasks/T001/worker_result.yaml").exists()
    assert (tmp_path / "tasks/T002/worker_result.yaml").exists()
    assert (tmp_path / "contracts/generated.schema.json").exists()
    task_two = load_yaml((tmp_path / "tasks/T002/task.yaml").read_text(encoding="utf-8"))
    assert task_two["data"]["contracts"][0]["path"] == "contracts/generated.schema.json"
    assert service.failed_task_ids(repo, ["T001", "T002"]) == []


def test_task_execution_service_executes_one_plan_task_with_contract_boundary(tmp_path):
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    goal = writer.write_goal(repo, "run_abc", "先定义 schema 再实现功能", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)
    service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)
    contracts = {}
    dispatched: list[str] = []

    first = service.execute_plan_task(
        repo,
        "run_abc",
        plan,
        plan.data.tasks[0],
        contracts,
        on_dispatch=lambda task_id, _handle: dispatched.append(task_id),
    )
    contracts.update(first.produced_contracts)

    assert first.task_id == "T001"
    assert dispatched == ["T001"]
    assert "contracts/generated.schema.json" in first.produced_contracts
    assert (tmp_path / "tasks/T001/task.yaml").exists()
    assert (tmp_path / "tasks/T001/worker_request.yaml").exists()
    assert (tmp_path / "tasks/T001/worker_result.yaml").exists()
    assert not (tmp_path / "tasks/T002/task.yaml").exists()

    second = service.execute_plan_task(
        repo,
        "run_abc",
        plan,
        plan.data.tasks[1],
        contracts,
        on_dispatch=lambda task_id, _handle: dispatched.append(task_id),
    )

    task_two = load_yaml((tmp_path / "tasks/T002/task.yaml").read_text(encoding="utf-8"))
    assert second.task_id == "T002"
    assert dispatched == ["T001", "T002"]
    assert task_two["data"]["contracts"][0]["path"] == "contracts/generated.schema.json"


def test_task_execution_service_records_real_git_diff_patch(tmp_path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "coductor@example.test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Coductor Test"],
        cwd=tmp_path,
        check=True,
    )
    tracked = tmp_path / "demo.txt"
    tracked.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "demo.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    repo = ArtifactRepository(tmp_path / ".coductor" / "runs" / "run_abc")
    writer = WorkflowArtifactWriter(tmp_path, config)
    goal = writer.write_goal(repo, "run_abc", "修改文件", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)
    service = TaskExecutionService(tmp_path, config, FileChangingBackend(tracked), writer)

    service.execute_plan_task(
        repo,
        "run_abc",
        plan,
        plan.data.tasks[0],
        {},
        on_dispatch=lambda *_: None,
    )

    patch_text = (repo.root / "tasks/T001/patch.diff").read_text(encoding="utf-8")
    worker_result = load_yaml(
        (repo.root / "tasks/T001/worker_result.yaml").read_text(encoding="utf-8")
    )
    assert "diff --git a/demo.txt b/demo.txt" in patch_text
    assert "-original" in patch_text
    assert "+changed" in patch_text
    assert worker_result["data"]["patch"]["bytes"] == len(patch_text.encode("utf-8"))


def test_task_execution_service_marks_protected_path_change_as_failed(tmp_path):
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    goal = writer.write_goal(repo, "run_abc", "修改配置", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)
    service = TaskExecutionService(tmp_path, config, EnvChangingBackend(), writer)

    service.execute_plan_task(
        repo,
        "run_abc",
        plan,
        plan.data.tasks[0],
        {},
        on_dispatch=lambda *_: None,
    )

    worker_result = load_yaml(
        (tmp_path / "tasks/T001/worker_result.yaml").read_text(encoding="utf-8")
    )
    assert worker_result["data"]["exit_reason"] == "failed"
    assert "protected path changed: .env" in worker_result["data"]["unresolved_issues"]


def test_task_execution_service_uses_budget_worker_timeout(tmp_path):
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.budgets.max_run_minutes = 3
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    goal = writer.write_goal(repo, "run_abc", "修改文件", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)
    service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)

    service.execute_plan_task(
        repo,
        "run_abc",
        plan,
        plan.data.tasks[0],
        {},
        on_dispatch=lambda *_: None,
    )

    request = load_yaml(
        (tmp_path / "tasks/T001/worker_request.yaml").read_text(encoding="utf-8")
    )
    assert request["data"]["timeout_seconds"] == 180
