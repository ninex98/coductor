"""Repository inspection node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def inspect_repository_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {
        "current_stage": "inspect_repository",
        "artifacts": {"01_repository_snapshot": "01_repository_snapshot.yaml"},
    }
