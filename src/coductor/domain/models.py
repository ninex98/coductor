"""Domain models that do not depend on CLI, storage, or backends."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from coductor.domain.enums import RunStatus


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    run_dir: str
    repair_attempts: int = 0
    message: str = ""
