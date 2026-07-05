"""Shared execution result for tool-backed verification checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ToolStatus = Literal["passed", "failed", "skipped", "timeout"]


@dataclass(frozen=True)
class ToolExecutionResult:
    status: ToolStatus
    exit_code: int | None
    duration_ms: int
    stdout: str
    stderr: str
    artifacts: list[str] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
