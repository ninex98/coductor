from __future__ import annotations

from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import load_yaml
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ExecutionMode
from coductor.services.task_execution_service import TaskExecutionService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


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
