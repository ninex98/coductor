from __future__ import annotations

from pathlib import Path

from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ExecutionMode
from coductor.storage.database import Database
from coductor.workflow.artifact_writer import WorkflowArtifactWriter
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.graph_runner import WorkflowGraphRunner
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
