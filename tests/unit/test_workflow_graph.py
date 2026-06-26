from __future__ import annotations

import sys

from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus, WorkerStatus
from coductor.services.repair_service import RepairService
from coductor.services.review_delivery_service import ReviewDeliveryService
from coductor.services.task_execution_service import TaskExecutionService
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.storage.database import Database
from coductor.workflow.artifact_writer import WorkflowArtifactWriter
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.graph import WORKFLOW_NODES, build_workflow_graph, compile_workflow_graph
from coductor.workflow.langgraph_checkpoint import langgraph_thread_config
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def test_build_workflow_graph_contains_expected_nodes() -> None:
    graph = build_workflow_graph()

    assert set(WORKFLOW_NODES).issubset(set(graph.nodes))


def test_compiled_workflow_graph_can_advance_state() -> None:
    compiled = build_workflow_graph().compile()

    result = compiled.invoke(
        WorkflowState(
            run_id="run_graph_000000000000000000001",
            status=RunStatus.RUNNING,
            raw_goal="只验证图状态",
        )
    )

    assert result["current_stage"] == "prepare_evidence"
    assert result["status"] == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result["artifacts"]["00_goal"] == "00_goal.yaml"
    assert result["artifacts"]["07_evidence"] == "07_evidence.yaml"


def test_compile_workflow_graph_accepts_optional_checkpointer(monkeypatch) -> None:
    graph = build_workflow_graph()
    checkpointer = object()
    calls: list[object] = []

    def recording_compile(*, checkpointer=None):
        calls.append(checkpointer)
        return "compiled"

    monkeypatch.setattr(graph, "compile", recording_compile)

    compiled = compile_workflow_graph(graph=graph, checkpointer=checkpointer)

    assert compiled == "compiled"
    assert calls == [checkpointer]
    assert langgraph_thread_config("run_abc") == {"configurable": {"thread_id": "run_abc"}}


def test_workflow_graph_routes_gate_failure_through_repair() -> None:
    compiled = build_workflow_graph().compile()

    result = compiled.invoke(
        WorkflowState(
            run_id="run_graph_000000000000000000002",
            status=RunStatus.RUNNING,
            raw_goal="只验证修复路由",
            gate_passed=False,
            max_repair_attempts=1,
        )
    )

    assert result["repair_attempts"] == 1
    assert result["gate_passed"] is True
    assert result["current_stage"] == "prepare_evidence"


def test_workflow_graph_can_execute_contextual_goal_node(tmp_path) -> None:
    run_id = "run_contextual_graph_000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=WorkflowArtifactWriter(tmp_path, CoductorConfig.default()),
        checkpoints=WorkflowCheckpointStore(
            Database(tmp_path / ".coductor" / "coductor.sqlite3"),
            tmp_path / ".coductor" / "runs",
        ),
    )
    compiled = build_workflow_graph(context=context).compile()

    compiled.invoke(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="验证真实图节点",
            run_dir=run_dir.as_posix(),
        )
    )

    assert repo.read("00_goal.yaml").data["raw_request"] == "验证真实图节点"
    assert (run_dir / "03_execution_plan.yaml").exists()


def test_contextual_workflow_graph_executes_task_dispatch_artifacts(tmp_path) -> None:
    run_id = "run_contextual_graph_dispatch_000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    writer = WorkflowArtifactWriter(tmp_path, config)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
        task_execution=TaskExecutionService(
            tmp_path,
            config,
            FakeCodingBackend(),
            writer,
        ),
    )
    compiled = build_workflow_graph(context=context).compile()

    compiled.invoke(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="创建网页小游戏",
            requested_mode="solo",
            run_dir=run_dir.as_posix(),
        )
    )

    assert (run_dir / "tasks/T001/task.yaml").exists()
    assert (run_dir / "tasks/T001/worker_request.yaml").exists()
    assert (run_dir / "tasks/T001/worker_result.yaml").exists()
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["task_T001"] == "tasks/T001/task.yaml"
    assert saved.artifacts["worker_result_T001"] == "tasks/T001/worker_result.yaml"


def test_contextual_workflow_graph_executes_happy_path_delivery(tmp_path) -> None:
    run_id = "run_contextual_graph_delivery_000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    backend = FakeCodingBackend()
    writer = WorkflowArtifactWriter(tmp_path, config)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
        task_execution=TaskExecutionService(tmp_path, config, backend, writer),
        verification=WorkflowVerificationService(tmp_path, config, writer),
        review_delivery=ReviewDeliveryService(tmp_path, config, backend, writer),
    )
    compiled = build_workflow_graph(context=context).compile()

    result = compiled.invoke(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="创建网页小游戏",
            requested_mode="solo",
            run_dir=run_dir.as_posix(),
        )
    )

    assert result["status"] == RunStatus.READY_FOR_HUMAN_REVIEW
    assert (run_dir / "04_integration.yaml").exists()
    assert (run_dir / "05_gate_report.yaml").exists()
    assert (run_dir / "06_review.yaml").exists()
    assert (run_dir / "07_evidence.yaml").exists()
    assert (run_dir / "delivery-report.md").exists()
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["07_evidence"] == "07_evidence.yaml"


def test_contextual_workflow_graph_persists_completed_pipeline_tasks(tmp_path) -> None:
    run_id = "run_contextual_graph_pipeline_complete_000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    backend = FakeCodingBackend()
    writer = WorkflowArtifactWriter(tmp_path, config)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
        task_execution=TaskExecutionService(tmp_path, config, backend, writer),
        verification=WorkflowVerificationService(tmp_path, config, writer),
        review_delivery=ReviewDeliveryService(tmp_path, config, backend, writer),
    )
    compiled = build_workflow_graph(context=context).compile()

    result = compiled.invoke(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="先定义 JSON schema，再基于上游 contract 实现下游功能",
            requested_mode="auto",
            run_dir=run_dir.as_posix(),
        )
    )

    integration = repo.read("04_integration.yaml").data
    evidence = repo.read("07_evidence.yaml").data
    saved = checkpoints.load(run_id)

    assert result["status"] == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result["completed_task_ids"] == ["T001", "T002"]
    assert integration["merged_tasks"] == ["T001", "T002"]
    assert evidence["completed_tasks"] == ["T001", "T002"]
    assert saved is not None
    assert saved.completed_task_ids == ["T001", "T002"]


class _FailingBackend:
    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        return WorkerHandle(worker_id=request.worker_id, thread_id="thread_failed")

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="worker failed",
            exit_reason="failed",
        )

    def cancel_worker(self, handle: WorkerHandle) -> None:
        return None

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.FAILED


def test_contextual_workflow_graph_stops_after_worker_failure(tmp_path) -> None:
    run_id = "run_contextual_graph_worker_failure_000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    backend = _FailingBackend()
    writer = WorkflowArtifactWriter(tmp_path, config)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
        task_execution=TaskExecutionService(tmp_path, config, backend, writer),
        verification=WorkflowVerificationService(tmp_path, config, writer),
        review_delivery=ReviewDeliveryService(tmp_path, config, backend, writer),
    )
    compiled = build_workflow_graph(context=context).compile()

    result = compiled.invoke(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="创建网页小游戏",
            requested_mode="solo",
            run_dir=run_dir.as_posix(),
        )
    )

    assert result["status"] == RunStatus.HUMAN_REQUIRED
    assert "worker failed" in result["last_error"]
    assert (run_dir / "tasks/T001/worker_result.yaml").exists()
    assert not (run_dir / "04_integration.yaml").exists()
    assert not (run_dir / "07_evidence.yaml").exists()


def test_contextual_workflow_graph_stops_pipeline_after_upstream_worker_failure(
    tmp_path,
) -> None:
    run_id = "run_contextual_graph_pipeline_failure_000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    backend = _FailingBackend()
    writer = WorkflowArtifactWriter(tmp_path, config)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
        task_execution=TaskExecutionService(tmp_path, config, backend, writer),
        verification=WorkflowVerificationService(tmp_path, config, writer),
        review_delivery=ReviewDeliveryService(tmp_path, config, backend, writer),
    )
    compiled = build_workflow_graph(context=context).compile()

    result = compiled.invoke(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="先定义 JSON schema，再基于上游 contract 实现下游功能",
            requested_mode="auto",
            run_dir=run_dir.as_posix(),
        )
    )

    assert result["status"] == RunStatus.HUMAN_REQUIRED
    assert result["last_error"] == "worker failed: T001"
    assert (run_dir / "tasks/T001/worker_result.yaml").exists()
    assert not (run_dir / "tasks/T002/task.yaml").exists()
    assert not (run_dir / "tasks/T002/worker_request.yaml").exists()
    assert not (run_dir / "tasks/T002/worker_result.yaml").exists()
    assert not (run_dir / "04_integration.yaml").exists()
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.status == RunStatus.HUMAN_REQUIRED
    assert saved.last_error == "worker failed: T001"


def test_contextual_workflow_graph_repairs_failed_gate(tmp_path) -> None:
    run_id = "run_contextual_graph_repair_000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    marker = tmp_path / "repair-marker"
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.workflow.max_repair_attempts = 2
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            command=(
                f'{sys.executable} -c "from pathlib import Path; import sys; '
                f"p=Path({str(marker)!r}); "
                'sys.exit(0 if p.exists() else 1)"'
            ),
            required=True,
            timeout_seconds=30,
        )
    ]
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )
    writer = WorkflowArtifactWriter(tmp_path, config)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
        task_execution=TaskExecutionService(tmp_path, config, backend, writer),
        verification=WorkflowVerificationService(tmp_path, config, writer),
        review_delivery=ReviewDeliveryService(tmp_path, config, backend, writer),
        repair=RepairService(tmp_path, config, backend, writer),
    )
    compiled = build_workflow_graph(context=context).compile()

    result = compiled.invoke(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_goal="修复失败测试",
            requested_mode="solo",
            run_dir=run_dir.as_posix(),
            max_repair_attempts=config.workflow.max_repair_attempts,
        )
    )

    assert result["status"] == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result["repair_attempts"] == 1
    assert (run_dir / "repairs/R001/repair_request.yaml").exists()
    assert (run_dir / "repairs/R001/repair_result.yaml").exists()
    assert (run_dir / "07_evidence.yaml").exists()
