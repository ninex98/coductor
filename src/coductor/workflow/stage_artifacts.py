"""Fixed YAML artifacts produced by Coductor workflow stages."""

from __future__ import annotations

from dataclasses import dataclass

from coductor.domain.enums import ArtifactType


@dataclass(frozen=True)
class StageArtifact:
    stage: str
    path_template: str
    artifact_type: ArtifactType


SUCCESS_STAGE_ARTIFACTS = [
    StageArtifact("collect_goal", "00_goal.yaml", ArtifactType.GOAL),
    StageArtifact(
        "inspect_repository",
        "01_repository_snapshot.yaml",
        ArtifactType.REPOSITORY_SNAPSHOT,
    ),
    StageArtifact("draft_spec", "02_spec.yaml", ArtifactType.SPECIFICATION),
    StageArtifact("create_execution_plan", "03_execution_plan.yaml", ArtifactType.EXECUTION_PLAN),
    StageArtifact("materialize_tasks", "tasks/{task_id}/task.yaml", ArtifactType.TASK),
    StageArtifact(
        "dispatch_tasks",
        "tasks/{task_id}/worker_request.yaml",
        ArtifactType.WORKER_REQUEST,
    ),
    StageArtifact(
        "dispatch_tasks",
        "tasks/{task_id}/worker_result.yaml",
        ArtifactType.WORKER_RESULT,
    ),
    StageArtifact("integrate_changes", "04_integration.yaml", ArtifactType.INTEGRATION),
    StageArtifact("run_quality_gates", "05_gate_report.yaml", ArtifactType.GATE_REPORT),
    StageArtifact("run_independent_review", "06_review.yaml", ArtifactType.REVIEW_REPORT),
    StageArtifact("prepare_evidence", "07_evidence.yaml", ArtifactType.EVIDENCE_BUNDLE),
]

CONTROL_STAGE_ARTIFACTS = [
    StageArtifact("prepare_release", "08_release_manifest.yaml", ArtifactType.RELEASE_MANIFEST),
]

REPAIR_STAGE_ARTIFACTS = [
    StageArtifact(
        "repair_failure",
        "repairs/{repair_id}/repair_request.yaml",
        ArtifactType.REPAIR_REQUEST,
    ),
    StageArtifact(
        "repair_failure",
        "repairs/{repair_id}/repair_result.yaml",
        ArtifactType.REPAIR_RESULT,
    ),
]

FAILURE_STOPS_BEFORE = {
    "worker_failed": [
        "04_integration.yaml",
        "05_gate_report.yaml",
        "06_review.yaml",
        "07_evidence.yaml",
    ],
}


def artifact_paths(artifacts: list[StageArtifact]) -> list[str]:
    return [artifact.path_template for artifact in artifacts]
