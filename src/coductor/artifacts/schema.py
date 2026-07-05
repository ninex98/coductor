"""JSON Schema generation for artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from coductor.artifacts.models import (
    ArtifactEnvelope,
    EvidenceBundleData,
    ExecutionPlanData,
    GateReportData,
    GoalData,
    GoalSatisfactionReportData,
    IntegrationData,
    RepairRequestData,
    RepositorySnapshotData,
    ReviewReportData,
    SpecificationData,
    TaskData,
    ToolRequestData,
    ToolResultData,
    VerificationPlanData,
    WorkerRequestData,
    WorkerResultData,
)

ARTIFACT_DATA_MODELS: dict[str, type[BaseModel]] = {
    "goal": GoalData,
    "repository_snapshot": RepositorySnapshotData,
    "specification": SpecificationData,
    "verification_plan": VerificationPlanData,
    "execution_plan": ExecutionPlanData,
    "task": TaskData,
    "worker_request": WorkerRequestData,
    "worker_result": WorkerResultData,
    "integration": IntegrationData,
    "gate_report": GateReportData,
    "tool_request": ToolRequestData,
    "tool_result": ToolResultData,
    "repair_request": RepairRequestData,
    "repair_result": WorkerResultData,
    "review_report": ReviewReportData,
    "goal_satisfaction_report": GoalSatisfactionReportData,
    "evidence_bundle": EvidenceBundleData,
}


def envelope_schema_for(name: str, data_model: type[BaseModel]) -> dict[str, Any]:
    title = "".join(part.title() for part in name.split("_")) + "Artifact"
    model = ArtifactEnvelope[data_model]  # type: ignore[valid-type]
    schema = model.model_json_schema()
    schema["title"] = title
    return schema


def generate_schemas(target_dir: Path) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in ARTIFACT_DATA_MODELS.items():
        path = target_dir / f"{name}.schema.json"
        path.write_text(
            json.dumps(
                envelope_schema_for(name, model),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
