"""Shared contract models for pipeline and parallel planning."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ContractArtifact(ContractModel):
    path: str
    kind: Literal["json_schema", "openapi", "event_schema", "type_definition"]
    sha256: str
    producer_task_id: str
