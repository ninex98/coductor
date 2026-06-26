from __future__ import annotations

from coductor.artifacts.models import GateReportData, GateResultData
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import WorkerHandle
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ExecutionMode, RunStatus
from coductor.services.repair_service import RepairService
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.storage.database import Database
from coductor.workflow.artifact_writer import WorkflowArtifactWriter
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.nodes.deliver import prepare_evidence_node
from coductor.workflow.nodes.execute import dispatch_tasks_node, materialize_tasks_node
from coductor.workflow.nodes.inspect import inspect_repository_node
from coductor.workflow.nodes.intake import collect_goal_node
from coductor.workflow.nodes.integrate import integrate_changes_node
from coductor.workflow.nodes.plan import create_execution_plan_node
from coductor.workflow.nodes.repair import repair_failure_node
from coductor.workflow.nodes.review import run_independent_review_node
from coductor.workflow.nodes.specify import draft_spec_node
from coductor.workflow.nodes.verify import run_quality_gates_node
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def test_front_half_nodes_record_stage_and_artifact_paths() -> None:
    state = WorkflowState(run_id="run_abc", raw_goal="修复示例函数")

    patches = [
        collect_goal_node(state),
        inspect_repository_node(state),
        draft_spec_node(state),
        create_execution_plan_node(state),
    ]

    assert patches == [
        {"current_stage": "collect_goal", "artifacts": {"00_goal": "00_goal.yaml"}},
        {
            "current_stage": "inspect_repository",
            "artifacts": {"01_repository_snapshot": "01_repository_snapshot.yaml"},
        },
        {"current_stage": "draft_spec", "artifacts": {"02_spec": "02_spec.yaml"}},
        {
            "current_stage": "create_execution_plan",
            "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
        },
    ]


def test_back_half_nodes_record_stage_and_artifact_paths() -> None:
    state = WorkflowState(run_id="run_abc", raw_goal="修复示例函数")

    patches = [
        materialize_tasks_node(state),
        dispatch_tasks_node(state),
        integrate_changes_node(state),
        run_quality_gates_node(state),
        repair_failure_node(state),
        run_independent_review_node(state),
        prepare_evidence_node(state),
    ]

    assert patches == [
        {"current_stage": "materialize_tasks"},
        {"current_stage": "dispatch_tasks"},
        {
            "current_stage": "integrate_changes",
            "artifacts": {"04_integration": "04_integration.yaml"},
        },
        {
            "current_stage": "run_quality_gates",
            "artifacts": {"05_gate_report": "05_gate_report.yaml"},
        },
        {
            "current_stage": "repair_failure",
            "repair_attempts": 1,
            "gate_passed": True,
        },
        {"current_stage": "run_independent_review", "artifacts": {"06_review": "06_review.yaml"}},
        {
            "current_stage": "prepare_evidence",
            "status": RunStatus.CREATED,
            "artifacts": {"07_evidence": "07_evidence.yaml"},
        },
    ]


def test_collect_goal_node_writes_goal_artifact_when_runtime_context_is_present(tmp_path) -> None:
    run_id = "run_goal_node_000000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=WorkflowArtifactWriter(tmp_path, CoductorConfig.default()),
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = collect_goal_node(state, context=context)

    assert patch == {
        "current_stage": "inspect_repository",
        "artifacts": {"00_goal": "00_goal.yaml"},
    }
    assert repo.read("00_goal.yaml").data["raw_request"] == "修复示例函数"
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["00_goal"] == "00_goal.yaml"
    assert saved.current_stage == "inspect_repository"


def test_inspect_repository_node_writes_snapshot_when_runtime_context_is_present(tmp_path) -> None:
    run_id = "run_inspect_node_0000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    writer = WorkflowArtifactWriter(tmp_path, CoductorConfig.default())
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(repo=repo, artifacts=writer, checkpoints=checkpoints)
    goal = writer.write_goal(repo, run_id, "修复示例函数", ExecutionMode.AUTO)
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = inspect_repository_node(state, context=context, goal=goal)

    assert patch == {
        "current_stage": "draft_spec",
        "artifacts": {"01_repository_snapshot": "01_repository_snapshot.yaml"},
    }
    assert repo.read("01_repository_snapshot.yaml", ArtifactType.REPOSITORY_SNAPSHOT)
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["01_repository_snapshot"] == "01_repository_snapshot.yaml"
    assert saved.current_stage == "draft_spec"


def test_draft_spec_node_writes_spec_when_runtime_context_is_present(tmp_path) -> None:
    run_id = "run_spec_node_000000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    writer = WorkflowArtifactWriter(tmp_path, CoductorConfig.default())
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(repo=repo, artifacts=writer, checkpoints=checkpoints)
    goal = writer.write_goal(repo, run_id, "修复示例函数", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, run_id, goal)
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = draft_spec_node(state, context=context, goal=goal, snapshot=snapshot)

    assert patch == {
        "current_stage": "create_execution_plan",
        "artifacts": {"02_spec": "02_spec.yaml"},
    }
    assert repo.read("02_spec.yaml", ArtifactType.SPECIFICATION)
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["02_spec"] == "02_spec.yaml"
    assert saved.current_stage == "create_execution_plan"


def test_create_execution_plan_node_writes_plan_when_runtime_context_is_present(
    tmp_path,
) -> None:
    run_id = "run_plan_node_000000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    writer = WorkflowArtifactWriter(tmp_path, CoductorConfig.default())
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(repo=repo, artifacts=writer, checkpoints=checkpoints)
    goal = writer.write_goal(repo, run_id, "修复示例函数", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, run_id, goal)
    spec = writer.write_spec(repo, run_id, goal, snapshot)
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = create_execution_plan_node(
        state,
        context=context,
        spec=spec,
        snapshot=snapshot,
        requested_mode=ExecutionMode.AUTO,
    )

    assert patch == {
        "current_stage": "create_execution_plan",
        "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
    }
    assert repo.read("03_execution_plan.yaml", ArtifactType.EXECUTION_PLAN)
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["03_execution_plan"] == "03_execution_plan.yaml"
    assert saved.current_stage == "create_execution_plan"


def test_materialize_tasks_node_saves_stage_when_runtime_context_is_present(tmp_path) -> None:
    run_id = "run_materialize_node_000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=WorkflowArtifactWriter(tmp_path, CoductorConfig.default()),
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = materialize_tasks_node(state, context=context)

    assert patch == {"current_stage": "materialize_tasks"}
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.current_stage == "materialize_tasks"


def test_dispatch_tasks_node_saves_stage_when_runtime_context_is_present(tmp_path) -> None:
    run_id = "run_dispatch_node_000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(
        repo=repo,
        artifacts=WorkflowArtifactWriter(tmp_path, CoductorConfig.default()),
        checkpoints=checkpoints,
    )
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = dispatch_tasks_node(state, context=context)

    assert patch == {"current_stage": "dispatch_tasks"}
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.current_stage == "dispatch_tasks"


def test_integrate_changes_node_writes_integration_when_runtime_context_is_present(
    tmp_path,
) -> None:
    run_id = "run_integration_node_000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    writer = WorkflowArtifactWriter(tmp_path, config)
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(repo=repo, artifacts=writer, checkpoints=checkpoints)
    goal = writer.write_goal(repo, run_id, "修复示例函数", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, run_id, goal)
    spec = writer.write_spec(repo, run_id, goal, snapshot)
    plan_artifact = writer.write_plan(repo, run_id, spec, snapshot, ExecutionMode.AUTO)
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = integrate_changes_node(
        state,
        context=context,
        plan=plan_artifact,
        completed_task_ids=["T001"],
        verification=WorkflowVerificationService(tmp_path, config, writer),
    )

    assert patch == {
        "current_stage": "run_quality_gates",
        "artifacts": {"04_integration": "04_integration.yaml"},
    }
    assert repo.read("04_integration.yaml", ArtifactType.INTEGRATION)
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["04_integration"] == "04_integration.yaml"
    assert saved.current_stage == "run_quality_gates"


def test_run_quality_gates_node_writes_gate_report_when_runtime_context_is_present(
    tmp_path,
) -> None:
    run_id = "run_gates_node_000000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    config.quality_gates = []
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    writer = WorkflowArtifactWriter(tmp_path, config)
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(repo=repo, artifacts=writer, checkpoints=checkpoints)
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = run_quality_gates_node(
        state,
        context=context,
        verification=WorkflowVerificationService(tmp_path, config, writer),
    )

    assert patch == {
        "current_stage": "run_quality_gates",
        "artifacts": {"05_gate_report": "05_gate_report.yaml"},
        "gate_passed": True,
    }
    assert repo.read("05_gate_report.yaml", ArtifactType.GATE_REPORT)
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.artifacts["05_gate_report"] == "05_gate_report.yaml"
    assert saved.current_stage == "run_quality_gates"
    assert saved.gate_passed is True


def test_repair_failure_node_writes_repair_artifacts_when_runtime_context_is_present(
    tmp_path,
) -> None:
    run_id = "run_repair_node_000000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    repo = ArtifactRepository(run_dir)
    config = CoductorConfig.default()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    writer = WorkflowArtifactWriter(tmp_path, config)
    checkpoints = WorkflowCheckpointStore(db, tmp_path / ".coductor" / "runs")
    context = WorkflowRuntimeContext(repo=repo, artifacts=writer, checkpoints=checkpoints)
    gate_report = writer.envelope(
        run_id=run_id,
        artifact_type=ArtifactType.GATE_REPORT,
        artifact_id_prefix="art_gates",
        status=ArtifactStatus.FAILED,
        producer={"kind": "tool", "name": "gate-runner"},
        data=GateReportData(
            base_commit="base",
            head_commit="head",
            gates=[
                GateResultData(
                    id="unit_tests",
                    required=True,
                    status="failed",
                    command="pytest",
                    exit_code=1,
                    duration_ms=10,
                    stdout_path="logs/unit.stdout.log",
                    stderr_path="logs/unit.stderr.log",
                    failure_fingerprint="abc",
                )
            ],
            required_gates_passed=False,
            next_action="repair",
        ),
    )
    repo.write("05_gate_report.yaml", gate_report)
    state = WorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_goal="修复示例函数",
        requested_mode="auto",
        run_dir=run_dir.as_posix(),
    )

    patch = repair_failure_node(
        state,
        context=context,
        builder_handle=WorkerHandle(worker_id="worker_T001", thread_id="thread_builder"),
        gate_report=gate_report,
        repair=RepairService(tmp_path, config, FakeCodingBackend(), writer),
        target_task_id="T001",
    )

    assert patch == {
        "current_stage": "run_quality_gates",
        "repair_attempts": 1,
        "artifacts": {
            "repair_request_R001": "repairs/R001/repair_request.yaml",
            "repair_result_R001": "repairs/R001/repair_result.yaml",
        },
    }
    assert repo.read("repairs/R001/repair_request.yaml", ArtifactType.REPAIR_REQUEST)
    assert repo.read("repairs/R001/repair_result.yaml", ArtifactType.REPAIR_RESULT)
    saved = checkpoints.load(run_id)
    assert saved is not None
    assert saved.repair_attempts == 1
    assert saved.current_stage == "run_quality_gates"
    assert saved.artifacts["repair_result_R001"] == "repairs/R001/repair_result.yaml"
