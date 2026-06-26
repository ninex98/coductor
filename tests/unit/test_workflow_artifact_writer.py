from __future__ import annotations

from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactType, ExecutionMode
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


def test_writer_creates_goal_artifact(tmp_path):
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, CoductorConfig.default())

    goal = writer.write_goal(repo, "run_abc", "修复示例函数", ExecutionMode.AUTO)

    assert goal.artifact_type == ArtifactType.GOAL
    assert goal.run_id == "run_abc"
    assert goal.data.raw_request == "修复示例函数"
    assert (tmp_path / "00_goal.yaml").exists()


def test_writer_creates_snapshot_spec_and_plan_with_lineage(tmp_path):
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, CoductorConfig.default())

    goal = writer.write_goal(repo, "run_abc", "先定义 schema 再实现功能", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)

    assert snapshot.artifact_type == ArtifactType.REPOSITORY_SNAPSHOT
    assert spec.artifact_type == ArtifactType.SPECIFICATION
    assert plan.artifact_type == ArtifactType.EXECUTION_PLAN
    assert snapshot.inputs[0].path == "00_goal.yaml"
    assert {item.path for item in spec.inputs} == {
        "00_goal.yaml",
        "01_repository_snapshot.yaml",
    }
    assert {item.path for item in plan.inputs} == {
        "02_spec.yaml",
        "01_repository_snapshot.yaml",
    }
    assert plan.data.strategy == "pipeline"
