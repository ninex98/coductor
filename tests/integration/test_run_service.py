from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus, WorkerStatus
from coductor.services.run_service import RunService
from coductor.workflow.graph_runner import WorkflowGraphRunner
from coductor.workflow.langgraph_checkpoint import langgraph_thread_config
from coductor.workflow.state import WorkflowState


def _config(command: str, *, max_repair_attempts: int = 2) -> CoductorConfig:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.workflow.max_repair_attempts = max_repair_attempts
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            stage="final",
            command=command,
            required=True,
            timeout_seconds=30,
        )
    ]
    return config


def test_fake_backend_run_repairs_after_initial_gate_failure(tmp_path: Path) -> None:
    marker = tmp_path / "repair-marker"
    command = (
        f'{sys.executable} -c "from pathlib import Path; import sys; '
        f"p=Path({str(marker)!r}); "
        'sys.exit(0 if p.exists() else 1)"'
    )
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )

    result = RunService(tmp_path, _config(command), backend=backend).run(
        "修复示例函数并补充测试"
    )

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result.repair_attempts == 1
    assert (tmp_path / ".coductor" / "runs" / result.run_id / "07_evidence.yaml").exists()
    assert (tmp_path / ".coductor" / "runs" / result.run_id / "delivery-report.md").exists()
    assert backend.review_thread_ids != backend.builder_thread_ids


def test_run_service_uses_contextual_graph_for_repair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "repair-marker"
    command = (
        f'{sys.executable} -c "from pathlib import Path; import sys; '
        f"p=Path({str(marker)!r}); "
        'sys.exit(0 if p.exists() else 1)"'
    )
    def fail_runner_repair(self, state, *, builder_handle, gate_report, repair, target_task_id):
        raise AssertionError("RunService should use contextual graph for repair")

    monkeypatch.setattr(WorkflowGraphRunner, "run_repair", fail_runner_repair)
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )

    result = RunService(tmp_path, _config(command), backend=backend).run(
        "修复示例函数并补充测试"
    )

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result.repair_attempts == 1
    assert (Path(result.run_dir) / "repairs/R001/repair_result.yaml").exists()


def test_run_stops_at_max_repair_attempts(tmp_path: Path) -> None:
    command = f"{sys.executable} -c 'import sys; sys.exit(1)'"

    result = RunService(
        tmp_path,
        _config(command, max_repair_attempts=1),
        backend=FakeCodingBackend(),
    ).run("修复示例函数并补充测试")

    assert result.status == RunStatus.HUMAN_REQUIRED
    assert result.repair_attempts == 1
    assert (tmp_path / ".coductor" / "runs" / result.run_id / "05_gate_report.yaml").exists()


class FailingBackend:
    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        return WorkerHandle(worker_id=request.worker_id, thread_id="thread_failed")

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="upstream 502",
            exit_reason="failed",
        )

    def cancel_worker(self, handle: WorkerHandle) -> None:
        return None

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.FAILED


def test_run_requires_human_when_worker_fails_even_without_gates(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []

    result = RunService(tmp_path, config, backend=FailingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.HUMAN_REQUIRED
    assert result.message == "worker failed: T001"
    run_dir = tmp_path / ".coductor" / "runs" / result.run_id
    assert (run_dir / "tasks" / "T001" / "worker_result.yaml").exists()
    assert not (run_dir / "07_evidence.yaml").exists()


def test_run_service_langgraph_checkpointer_returns_none_when_dependency_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = RunService(tmp_path, CoductorConfig.default(), backend=FakeCodingBackend())

    def missing_saver(connection: sqlite3.Connection) -> object:
        del connection
        from coductor.workflow.langgraph_checkpoint import (
            LangGraphSqliteCheckpointUnavailable,
        )

        raise LangGraphSqliteCheckpointUnavailable("missing")

    monkeypatch.setattr(
        "coductor.workflow.langgraph_checkpoint.create_langgraph_sqlite_saver",
        missing_saver,
    )

    assert service.langgraph_checkpointer() is None


def test_run_service_langgraph_checkpointer_uses_coductor_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = RunService(tmp_path, CoductorConfig.default(), backend=FakeCodingBackend())
    received_paths: list[str] = []

    class FakeSaver:
        pass

    def fake_saver(connection: sqlite3.Connection) -> FakeSaver:
        row = connection.execute("pragma database_list").fetchone()
        received_paths.append(row[2])
        return FakeSaver()

    monkeypatch.setattr(
        "coductor.workflow.langgraph_checkpoint.create_langgraph_sqlite_saver",
        fake_saver,
    )

    saver = service.langgraph_checkpointer()

    assert isinstance(saver, FakeSaver)
    assert received_paths == [(tmp_path / ".coductor" / "coductor.sqlite3").as_posix()]


def test_run_service_compile_langgraph_uses_optional_checkpointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = RunService(tmp_path, CoductorConfig.default(), backend=FakeCodingBackend())
    checkpointer = object()
    received: list[object | None] = []

    monkeypatch.setattr(service.langgraph_checkpoints, "checkpointer", lambda: checkpointer)

    def fake_compile_workflow_graph(*, checkpointer=None):
        received.append(checkpointer)
        return "compiled"

    monkeypatch.setattr(
        "coductor.workflow.langgraph_checkpoint.compile_workflow_graph",
        fake_compile_workflow_graph,
    )

    assert service.compile_langgraph() == "compiled"
    assert received == [checkpointer]


def test_run_service_compile_langgraph_allows_missing_checkpointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = RunService(tmp_path, CoductorConfig.default(), backend=FakeCodingBackend())
    received: list[object | None] = []

    monkeypatch.setattr(service.langgraph_checkpoints, "checkpointer", lambda: None)

    def fake_compile_workflow_graph(*, checkpointer=None):
        received.append(checkpointer)
        return "compiled"

    monkeypatch.setattr(
        "coductor.workflow.langgraph_checkpoint.compile_workflow_graph",
        fake_compile_workflow_graph,
    )

    assert service.compile_langgraph() == "compiled"
    assert received == [None]


def test_run_service_open_langgraph_closes_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = RunService(tmp_path, CoductorConfig.default(), backend=FakeCodingBackend())
    closed: list[bool] = []

    @contextmanager
    def fake_open_graph():
        try:
            yield "compiled"
        finally:
            closed.append(True)

    monkeypatch.setattr(service.langgraph_checkpoints, "open_graph", fake_open_graph)

    with service.open_langgraph() as graph:
        assert graph == "compiled"
        assert closed == []

    assert closed == [True]


def test_run_service_save_checkpoint_updates_langgraph_sqlite_state(
    tmp_path: Path,
) -> None:
    service = RunService(tmp_path, CoductorConfig.default(), backend=FakeCodingBackend())
    run_id = "run_langgraph_checkpoint_000000000001"

    service.save_checkpoint(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="验证 LangGraph 原生 checkpoint",
            current_stage="draft_spec",
            artifacts={"02_spec": "02_spec.yaml"},
        )
    )

    with service.open_langgraph() as graph:
        assert graph is not None
        snapshot = graph.get_state(langgraph_thread_config(run_id))

    assert snapshot.values["run_id"] == run_id
    assert snapshot.values["current_stage"] == "draft_spec"
    assert snapshot.values["artifacts"]["02_spec"] == "02_spec.yaml"


def test_run_service_uses_contextual_graph_for_front_half(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(f"{sys.executable} -c 'print(1)'")

    def fail_runner_front_half(self, state, *, requested_mode):
        raise AssertionError("RunService should use contextual graph for front half")

    monkeypatch.setattr(WorkflowGraphRunner, "run_front_half", fail_runner_front_half)

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert (Path(result.run_dir) / "03_execution_plan.yaml").exists()


def test_run_service_uses_contextual_graph_for_no_gate_happy_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []

    def fail_runner_front_half(self, state, *, requested_mode):
        raise AssertionError("RunService should use contextual graph for no-gate happy path")

    monkeypatch.setattr(WorkflowGraphRunner, "run_front_half", fail_runner_front_half)

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert (Path(result.run_dir) / "07_evidence.yaml").exists()


def test_run_service_uses_contextual_graph_for_gate_repair_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "repair-marker"
    command = (
        f'{sys.executable} -c "from pathlib import Path; import sys; '
        f"p=Path({str(marker)!r}); "
        'sys.exit(0 if p.exists() else 1)"'
    )
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )

    def fail_runner_repair(self, state, *, builder_handle, gate_report, repair, target_task_id):
        raise AssertionError("RunService should use contextual graph for gate repair path")

    monkeypatch.setattr(WorkflowGraphRunner, "run_repair", fail_runner_repair)

    result = RunService(tmp_path, _config(command), backend=backend).run("修复失败测试")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result.repair_attempts == 1
    assert (Path(result.run_dir) / "repairs/R001/repair_result.yaml").exists()


def test_run_service_does_not_create_workflow_graph_runner_for_default_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(f"{sys.executable} -c 'print(1)'")

    def fail_runner_init(self, *args, **kwargs):
        raise AssertionError("RunService should use contextual graph")

    monkeypatch.setattr(WorkflowGraphRunner, "__init__", fail_runner_init)

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW


def test_run_service_uses_contextual_graph_for_task_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(f"{sys.executable} -c 'print(1)'")

    def fail_runner_task_execution(self, state, *, plan, tasks, on_dispatch=None):
        raise AssertionError("RunService should use contextual graph for tasks")

    monkeypatch.setattr(
        WorkflowGraphRunner,
        "run_task_execution",
        fail_runner_task_execution,
    )

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert (Path(result.run_dir) / "tasks/T001/worker_result.yaml").exists()


def test_run_service_reports_dispatch_progress_from_task_runner(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    events: list[tuple[str, str]] = []

    result = RunService(
        tmp_path,
        config,
        backend=FakeCodingBackend(),
        progress=lambda stage, message: events.append((stage, message)),
    ).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert ("dispatch_tasks", "dispatch T001") in events


def test_run_service_uses_contextual_graph_for_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(f"{sys.executable} -c 'print(1)'")

    def fail_runner_integration(
        self,
        state,
        *,
        plan,
        completed_task_ids,
        verification,
    ):
        raise AssertionError("RunService should use contextual graph for integration")

    def fail_runner_quality_gates(self, state, *, verification):
        raise AssertionError("RunService should use contextual graph for gates")

    monkeypatch.setattr(WorkflowGraphRunner, "run_integration", fail_runner_integration)
    monkeypatch.setattr(WorkflowGraphRunner, "run_quality_gates", fail_runner_quality_gates)

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert (Path(result.run_dir) / "04_integration.yaml").exists()
    assert (Path(result.run_dir) / "05_gate_report.yaml").exists()


def test_run_service_uses_contextual_graph_for_delivery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(f"{sys.executable} -c 'print(1)'")

    def fail_runner_review(self, state, *, review):
        raise AssertionError("RunService should use contextual graph for review")

    def fail_runner_evidence(self, state, *, evidence):
        raise AssertionError("RunService should use contextual graph for evidence")

    monkeypatch.setattr(WorkflowGraphRunner, "run_review", fail_runner_review)
    monkeypatch.setattr(WorkflowGraphRunner, "run_evidence", fail_runner_evidence)

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert (Path(result.run_dir) / "06_review.yaml").exists()
    assert (Path(result.run_dir) / "07_evidence.yaml").exists()
