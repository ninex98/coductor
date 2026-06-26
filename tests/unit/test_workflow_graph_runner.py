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
from coductor.workflow.nodes import (
    execute,
    inspect,
    intake,
    integrate,
    plan,
    repair,
    review,
    specify,
    verify,
)
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


def test_graph_runner_uses_draft_spec_node_for_specification(
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
    original = specify.draft_spec_node

    def recording_draft_spec_node(state, *, context=None, goal=None, snapshot=None):
        calls.append(state.run_id)
        return original(state, context=context, goal=goal, snapshot=snapshot)

    monkeypatch.setattr(specify, "draft_spec_node", recording_draft_spec_node)

    runner.run_front_half(state, requested_mode=ExecutionMode.AUTO)

    assert calls == [run_id]


def test_graph_runner_uses_create_execution_plan_node_for_plan(
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
    original = plan.create_execution_plan_node

    def recording_create_execution_plan_node(
        state,
        *,
        context=None,
        spec=None,
        snapshot=None,
        requested_mode=None,
    ):
        calls.append(state.run_id)
        return original(
            state,
            context=context,
            spec=spec,
            snapshot=snapshot,
            requested_mode=requested_mode,
        )

    monkeypatch.setattr(
        plan,
        "create_execution_plan_node",
        recording_create_execution_plan_node,
    )

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


def test_graph_runner_uses_materialize_tasks_node_before_task_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    _goal, _snapshot, _spec, plan_artifact, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)
    calls: list[str] = []
    original = execute.materialize_tasks_node

    def recording_materialize_tasks_node(state, *, context=None):
        calls.append(state.run_id)
        return original(state, context=context)

    monkeypatch.setattr(execute, "materialize_tasks_node", recording_materialize_tasks_node)

    runner.run_task_execution(state, plan=plan_artifact, tasks=service)

    assert calls == [run_id]


def test_graph_runner_uses_dispatch_tasks_node_when_worker_dispatches(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    _goal, _snapshot, _spec, plan_artifact, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)
    calls: list[str] = []
    original = execute.dispatch_tasks_node

    def recording_dispatch_tasks_node(state, *, context=None):
        calls.append(state.run_id)
        return original(state, context=context)

    monkeypatch.setattr(execute, "dispatch_tasks_node", recording_dispatch_tasks_node)

    runner.run_task_execution(state, plan=plan_artifact, tasks=service)

    assert calls == [run_id]


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


def test_graph_runner_uses_integrate_changes_node_for_integration(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    _goal, _snapshot, _spec, plan_artifact, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    verification = WorkflowVerificationService(tmp_path, config, writer)
    calls: list[str] = []
    original = integrate.integrate_changes_node

    def recording_integrate_changes_node(
        state,
        *,
        context=None,
        plan=None,
        completed_task_ids=None,
        verification=None,
    ):
        calls.append(state.run_id)
        return original(
            state,
            context=context,
            plan=plan,
            completed_task_ids=completed_task_ids,
            verification=verification,
        )

    monkeypatch.setattr(integrate, "integrate_changes_node", recording_integrate_changes_node)

    runner.run_integration(
        state,
        plan=plan_artifact,
        completed_task_ids=["T001"],
        verification=verification,
    )

    assert calls == [run_id]


def test_graph_runner_uses_quality_gates_node_for_gate_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    verification = WorkflowVerificationService(tmp_path, config, writer)
    calls: list[str] = []
    original = verify.run_quality_gates_node

    def recording_run_quality_gates_node(state, *, context=None, verification=None):
        calls.append(state.run_id)
        return original(state, context=context, verification=verification)

    monkeypatch.setattr(verify, "run_quality_gates_node", recording_run_quality_gates_node)

    gate_report, state = runner.run_quality_gates(state, verification=verification)

    assert calls == [run_id]
    assert gate_report.data.required_gates_passed
    assert state.artifacts["05_gate_report"] == "05_gate_report.yaml"


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


def test_graph_runner_uses_review_node_for_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    _goal, _snapshot, _spec, plan_artifact, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    task_service = TaskExecutionService(tmp_path, config, FakeCodingBackend(), writer)
    executed, state = runner.run_task_execution(state, plan=plan_artifact, tasks=task_service)
    completed_task_ids = [task.task_id for task in executed]
    verification = WorkflowVerificationService(tmp_path, config, writer)
    state = runner.run_integration(
        state,
        plan=plan_artifact,
        completed_task_ids=completed_task_ids,
        verification=verification,
    )
    gate_report, state = runner.run_quality_gates(state, verification=verification)
    delivery = ReviewDeliveryService(tmp_path, config, FakeCodingBackend(), writer)
    calls: list[str] = []
    original = review.run_independent_review_node

    def recording_run_independent_review_node(state, *, context=None, review=None):
        calls.append(state.run_id)
        return original(state, context=context, review=review)

    monkeypatch.setattr(
        review,
        "run_independent_review_node",
        recording_run_independent_review_node,
    )

    review_report, state = runner.run_review(
        state,
        review=lambda: delivery.review(repo, run_id, gate_report, completed_task_ids),
    )

    assert calls == [run_id]
    assert review_report.data.verdict == "pass"


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


def test_graph_runner_uses_repair_failure_node_for_repair(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    _goal, _snapshot, _spec, plan_artifact, state = runner.run_front_half(
        state,
        requested_mode=ExecutionMode.SOLO,
    )
    task_service = TaskExecutionService(tmp_path, config, backend, writer)
    executed, state = runner.run_task_execution(state, plan=plan_artifact, tasks=task_service)
    verification = WorkflowVerificationService(tmp_path, config, writer)
    gate_report, state = runner.run_quality_gates(state, verification=verification)
    repair_service = RepairService(tmp_path, config, backend, writer)
    calls: list[str] = []
    original = repair.repair_failure_node

    def recording_repair_failure_node(
        state,
        *,
        context=None,
        builder_handle=None,
        gate_report=None,
        repair=None,
        target_task_id=None,
    ):
        calls.append(state.run_id)
        return original(
            state,
            context=context,
            builder_handle=builder_handle,
            gate_report=gate_report,
            repair=repair,
            target_task_id=target_task_id,
        )

    monkeypatch.setattr(repair, "repair_failure_node", recording_repair_failure_node)

    runner.run_repair(
        state,
        builder_handle=executed[-1].handle,
        gate_report=gate_report,
        repair=repair_service,
        target_task_id=executed[-1].task_id,
    )

    assert calls == [run_id]
