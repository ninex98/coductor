"""Quality gate models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QualityGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    stage: str = "final"
    command: str
    required: bool = True
    timeout_seconds: int = 300
