from __future__ import annotations

import sys

from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig, QualityGateConfig, ToolCheckConfig
from coductor.domain.enums import ExecutionMode
from coductor.services.workflow_verification_service import WorkflowVerificationService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


def test_verification_service_writes_integration_and_gate_report(tmp_path):
    config = CoductorConfig.default()
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            command=f"{sys.executable} -c 'print(1)'",
            required=True,
            timeout_seconds=30,
        )
    ]
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    goal = writer.write_goal(repo, "run_abc", "修复示例函数", ExecutionMode.AUTO)
    snapshot = writer.write_snapshot(repo, "run_abc", goal)
    spec = writer.write_spec(repo, "run_abc", goal, snapshot)
    plan = writer.write_plan(repo, "run_abc", spec, snapshot, ExecutionMode.AUTO)
    service = WorkflowVerificationService(tmp_path, config, writer)

    service.write_integration(repo, "run_abc", plan, ["T001"])
    gate_report = service.run_gates(repo, "run_abc")

    assert (tmp_path / "04_integration.yaml").exists()
    assert (tmp_path / "05_gate_report.yaml").exists()
    assert gate_report.data.required_gates_passed


def test_verification_service_runs_configured_tool_checks(tmp_path):
    config = CoductorConfig.default()
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            command=f"{sys.executable} -c 'print(1)'",
            required=True,
            timeout_seconds=30,
        )
    ]
    config.tool_checks = [
        ToolCheckConfig(
            id="browser-smoke",
            tool="browser",
            command=f"{sys.executable} -c 'print(\"browser ok\")'",
            timeout_seconds=30,
        )
    ]
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    service = WorkflowVerificationService(tmp_path, config, writer)

    service.run_gates(repo, "run_abc")

    assert (tmp_path / "tool_runs/browser-smoke/tool_request.yaml").exists()
    assert (tmp_path / "tool_runs/browser-smoke/tool_result.yaml").exists()
