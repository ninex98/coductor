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


def test_writer_derives_specific_spec_and_plan_from_goal_and_config(tmp_path):
    config = CoductorConfig.default()
    config.quality_gates = []
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)

    goal = writer.write_goal(
        repo,
        "run_abc",
        "修复 CLI review evidence 状态误报，并补充测试",
        ExecutionMode.AUTO,
    )
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)

    statements = [criterion.statement for criterion in spec.data.acceptance_criteria]
    assert any("CLI" in statement for statement in statements)
    assert any("review" in statement.lower() for statement in statements)
    assert any("evidence" in statement.lower() for statement in statements)
    assert any("测试" in statement for statement in statements)
    assert spec.data.unresolved_questions == []
    task = plan.data.tasks[0]
    assert set(task.acceptance_criteria) == {
        criterion.id for criterion in spec.data.acceptance_criteria
    }
    assert "tests/**" in task.allowed_paths
    assert "unit_tests" not in task.quality_gates
