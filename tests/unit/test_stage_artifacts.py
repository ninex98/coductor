from __future__ import annotations

from coductor.workflow.stage_artifacts import (
    CONTROL_STAGE_ARTIFACTS,
    FAILURE_STOPS_BEFORE,
    REPAIR_STAGE_ARTIFACTS,
    SUCCESS_STAGE_ARTIFACTS,
    artifact_paths,
)


def test_success_stage_artifacts_define_fixed_yaml_contract() -> None:
    paths = artifact_paths(SUCCESS_STAGE_ARTIFACTS)

    assert "00_goal.yaml" in paths
    assert "01_repository_snapshot.yaml" in paths
    assert "02_spec.yaml" in paths
    assert "03_execution_plan.yaml" in paths
    assert "tasks/{task_id}/task.yaml" in paths
    assert "tasks/{task_id}/worker_request.yaml" in paths
    assert "tasks/{task_id}/worker_result.yaml" in paths
    assert "04_integration.yaml" in paths
    assert "05_gate_report.yaml" in paths
    assert "06_review.yaml" in paths
    assert "07_evidence.yaml" in paths


def test_repair_stage_artifacts_define_fixed_yaml_contract() -> None:
    paths = artifact_paths(REPAIR_STAGE_ARTIFACTS)

    assert paths == [
        "repairs/{repair_id}/repair_request.yaml",
        "repairs/{repair_id}/repair_result.yaml",
    ]


def test_control_stage_artifacts_define_fixed_yaml_contract() -> None:
    paths = artifact_paths(CONTROL_STAGE_ARTIFACTS)

    assert paths == ["08_release_manifest.yaml"]


def test_worker_failure_stops_before_downstream_artifacts() -> None:
    assert FAILURE_STOPS_BEFORE["worker_failed"] == [
        "04_integration.yaml",
        "05_gate_report.yaml",
        "06_review.yaml",
        "07_evidence.yaml",
    ]
