"""Specification node helpers."""

from __future__ import annotations

from typing import Any

from coductor.workflow.state import WorkflowState


def draft_spec_node(state: WorkflowState) -> dict[str, Any]:
    del state
    return {"current_stage": "draft_spec", "artifacts": {"02_spec": "02_spec.yaml"}}
