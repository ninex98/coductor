from __future__ import annotations

from pathlib import Path

from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ExecutionMode, ExecutionStrategy
from coductor.services.repair_service import RepairService
from coductor.services.review_delivery_service import ReviewDeliveryService
from coductor.services.task_execution_service import TaskExecutionService
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.storage.database import Database
from coductor.workflow.artifact_writer import WorkflowArtifactWriter
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.graph_runner import WorkflowGraphRunner
from coductor.workflow.nodes import inspect, intake
from coductor.workflow.state import WorkflowState


def test_graph_runner_executes_front_half_artifacts_and_checkpoint(tmp_path: Path) -> None:
    run_id = "run_abc"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    runner = WorkflowGraphRunner(
        repo=repo,
        artifacts=WorkflowArtifactWriter(tmp_path, config),
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status="running",
        raw_goal="先定义 schema 再实现功能",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    goal, snapshot, spec, plan, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.AUTO,
    )

    assert goal.data.raw_request == "先定义 schema 再实现功能"
    assert plan.data.strategy == "pipeline"
    assert state.artifacts["03_execution_plan"] == "03_execution_plan.yaml"
    assert state.current_stage == "create_execution_plan"
    assert (run_dir / "00_goal.yaml").exists()
    assert (run_dir / "03_execution_plan.yaml").exists()
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["02_spec"] == "02_spec.yaml"


def test_graph_runner_uses_collect_goal_node_for_goal_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_id = "run_abc"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    runner = WorkflowGraphRunner(
        repo=repo,
        artifacts=WorkflowArtifactWriter(tmp_path, config),
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status="running",
        raw_goal="创建网页小游戏",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )
    calls: list[str] = []
    original = intake.collect_goal_node

    def recording_collect_goal_node(state, *, context=None):
        calls.append(state.run_id)
        return original(state, context=context)

    monkeypatch.setattr(intake, "collect_goal_node", recording_collect_goal_node)

    runner.run_front_half(state, requested_mode=ExecutionMode.AUTO)

    assert calls == [run_id]


def test_graph_runner_uses_inspect_repository_node_for_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_id = "run_abc"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    runner = WorkflowGraphRunner(
        repo=repo,
        artifacts=WorkflowArtifactWriter(tmp_path, config),
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status="running",
        raw_goal="创建网页小游戏",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )
    calls: list[str] = []
    original = inspect.inspect_repository_node

    def recording_inspect_repository_node(state, *, context=None, goal=None):
        calls.append(state.run_id)
        return original(state, context=context, goal=goal)

    monkeypatch.setattr(inspect, "inspect_repository_node", recording_inspect_repository_node)

    runner.run_front_half(state, requested_mode=ExecutionMode.AUTO)

    assert calls == [run_id]


def test_graph_runner_executes_plan_tasks_and_checkpoint(tmp_path: Path) -> None:
    run_id = "run_abc"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    writer = WorkflowArtifactWriter(tmp_path, config)
    runner = WorkflowGraphRunner(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status="running",
        raw_goal="创建网页小游戏",
        requested_mode="solo",
        run_dir=run_dir.as_posix(),
    )
    _goal, _snapshot, _spec, plan, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)

    executed, state = runner.run_task_execution(state, plan=plan, tasks=service)

    assert [task.task_id for task in executed] == ["T001"]
    assert state.current_stage == "dispatch_tasks"
    assert state.artifacts["task_T001"] == "tasks/T001/task.yaml"
    assert state.artifacts["worker_result_T001"] == "tasks/T001/worker_result.yaml"
    assert (run_dir / "tasks/T001/task.yaml").exists()
    assert (run_dir / "tasks/T001/worker_result.yaml").exists()
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["worker_result_T001"] == "tasks/T001/worker_result.yaml"


def test_graph_runner_runs_integration_and_quality_gates(tmp_path: Path) -> None:
    run_id = "run_abc"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.quality_gates = []
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    writer = WorkflowArtifactWriter(tmp_path, config)
    runner = WorkflowGraphRunner(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status="running",
        raw_goal="创建网页小游戏",
        requested_mode="solo",
        run_dir=run_dir.as_posix(),
    )
    _goal, _snapshot, _spec, plan, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    verification = WorkflowVerificationService(tmp_path, config, writer)

    state = runner.run_integration(
        state,
        plan=plan,
        completed_task_ids=["T001"],
        verification=verification,
    )
    gate_report, state = runner.run_quality_gates(state, verification=verification)

    assert gate_report.data.required_gates_passed
    assert state.current_stage == "run_quality_gates"
    assert state.artifacts["04_integration"] == "04_integration.yaml"
    assert state.artifacts["05_gate_report"] == "05_gate_report.yaml"
    assert (run_dir / "04_integration.yaml").exists()
    assert (run_dir / "05_gate_report.yaml").exists()
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["05_gate_report"] == "05_gate_report.yaml"


def test_graph_runner_runs_review_and_evidence(tmp_path: Path) -> None:
    run_id = "run_abc"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    writer = WorkflowArtifactWriter(tmp_path, config)
    runner = WorkflowGraphRunner(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status="running",
        raw_goal="创建网页小游戏",
        requested_mode="solo",
        run_dir=run_dir.as_posix(),
    )
    goal, _snapshot, _spec, plan, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    task_service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)
    executed, state = runner.run_task_execution(state, plan=plan, tasks=task_service)
    completed_task_ids = [task.task_id for task in executed]
    verification = WorkflowVerificationService(tmp_path, config, writer)
    state = runner.run_integration(
        state,
        plan=plan,
        completed_task_ids=completed_task_ids,
        verification=verification,
    )
    gate_report, state = runner.run_quality_gates(state, verification=verification)
    delivery = ReviewDeliveryService(tmp_path, config, FakeCodingBackend(), writer)

    review, state = runner.run_review(
        state,
        review=lambda: delivery.review(repo, run_id, gate_report, completed_task_ids),
    )
    evidence, state = runner.run_evidence(
        state,
        evidence=lambda: delivery.evidence(
            repo,
            run_id,
            goal,
            gate_report,
            review,
            ExecutionStrategy.SOLO,
            completed_task_ids,
        ),
    )

    assert review.data.verdict == "pass"
    assert evidence.data.final_status == "ready_for_human_review"
    assert state.status == "ready_for_human_review"
    assert state.current_stage == "prepare_evidence"
    assert state.artifacts["06_review"] == "06_review.yaml"
    assert state.artifacts["07_evidence"] == "07_evidence.yaml"
    assert (run_dir / "06_review.yaml").exists()
    assert (run_dir / "07_evidence.yaml").exists()
    assert (run_dir / "delivery-report.md").exists()


def test_graph_runner_runs_repair_and_checkpoint(tmp_path: Path) -> None:
    run_id = "run_abc"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    writer = WorkflowArtifactWriter(tmp_path, config)
    backend = FakeCodingBackend()
    runner = WorkflowGraphRunner(
        repo=repo,
        artifacts=writer,
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status="running",
        raw_goal="创建网页小游戏",
        requested_mode="solo",
        run_dir=run_dir.as_posix(),
    )
    _goal, _snapshot, _spec, plan, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    task_service = TaskExecutionService(tmp_path, config, backend, writer)
    executed, state = runner.run_task_execution(state, plan=plan, tasks=task_service)
    verification = WorkflowVerificationService(tmp_path, config, writer)
    gate_report, state = runner.run_quality_gates(state, verification=verification)
    repair_service = RepairService(tmp_path, config, backend, writer)

    state = runner.run_repair(
        state,
        builder_handle=executed[-1].handle,
        gate_report=gate_report,
        repair=repair_service,
        target_task_id=executed[-1].task_id,
    )

    assert state.current_stage == "run_quality_gates"
    assert state.repair_attempts == 1
    assert state.artifacts["repair_request_R001"] == "repairs/R001/repair_request.yaml"
    assert state.artifacts["repair_result_R001"] == "repairs/R001/repair_result.yaml"
    assert (run_dir / "repairs/R001/repair_request.yaml").exists()
    assert (run_dir / "repairs/R001/repair_result.yaml").exists()
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["repair_result_R001"] == "repairs/R001/repair_result.yaml"
