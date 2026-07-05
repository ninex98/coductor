from __future__ import annotations

import sys

from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig, QualityGateConfig, ToolCheckConfig
from coductor.domain.enums import ArtifactType, ExecutionMode
from coductor.services.workflow_verification_service import WorkflowVerificationService
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
    verification_plan = writer.write_verification_plan(repo, "run_abc", spec)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)

    assert snapshot.artifact_type == ArtifactType.REPOSITORY_SNAPSHOT
    assert spec.artifact_type == ArtifactType.SPECIFICATION
    assert verification_plan.artifact_type == ArtifactType.VERIFICATION_PLAN
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
    assert verification_plan.inputs[0].path == "02_spec.yaml"
    assert verification_plan.data.items[0].evidence_paths == ["05_gate_report.yaml"]
    assert plan.data.strategy == "pipeline"


def test_writer_includes_tool_checks_in_verification_plan(tmp_path):
    config = CoductorConfig.default()
    config.tool_checks = [
        ToolCheckConfig(
            id="browser smoke",
            tool="browser",
            command=f"{sys.executable} -c 'print(1)'",
        )
    ]
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)

    goal = writer.write_goal(repo, "run_abc", "修复示例函数", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    verification_plan = writer.write_verification_plan(repo, "run_abc", spec)

    item = verification_plan.data.items[0]

    assert item.tool == "quality_gate+tool_check"
    assert "tool_runs/browser-smoke/tool_result.yaml" in item.evidence_paths


def test_writer_creates_image_generation_verification_item(tmp_path):
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)

    goal = writer.write_goal(repo, "run_abc", "为首页生成一张产品背景图片", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    verification_plan = writer.write_verification_plan(repo, "run_abc", spec)

    image_item = next(
        item for item in verification_plan.data.items if item.tool == "image_generation"
    )

    assert image_item.commands == ["image-asset-request"]
    assert image_item.evidence_paths == ["tool_runs/image_asset_ac002/tool_result.yaml"]


def test_goal_satisfaction_rejects_failed_tool_result(tmp_path):
    config = CoductorConfig.default()
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            command=f"{sys.executable} -c 'print(1)'",
            timeout_seconds=30,
        )
    ]
    config.tool_checks = [
        ToolCheckConfig(
            id="browser-smoke",
            tool="browser",
            command=f"{sys.executable} -c 'import sys; sys.exit(7)'",
            timeout_seconds=30,
        )
    ]
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    goal = writer.write_goal(repo, "run_abc", "修复示例函数", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    verification_plan = writer.write_verification_plan(repo, "run_abc", spec)
    gate_report = WorkflowVerificationService(tmp_path, config, writer).run_gates(
        repo,
        "run_abc",
    )

    satisfaction = writer.write_goal_satisfaction(
        repo,
        "run_abc",
        verification_plan,
        gate_report,
    )

    assert satisfaction.data.verdict == "not_satisfied"
    assert satisfaction.data.criterion_results[0].status == "not_satisfied"
    assert "planned tool evidence failed" in satisfaction.data.criterion_results[0].reason


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
