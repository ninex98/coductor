"""Domain exceptions with user-facing recovery context."""

from __future__ import annotations


class CoductorError(Exception):
    """Base exception for recoverable Coductor failures."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        run_id: str | None = None,
        recoverable: bool = True,
        next_command: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.run_id = run_id
        self.recoverable = recoverable
        self.next_command = next_command

    def to_display(self) -> str:
        run = self.run_id or "unknown"
        next_step = self.next_command or "coductor status"
        recovery = "可恢复" if self.recoverable else "不可自动恢复"
        return (
            f"阶段: {self.stage}\n"
            f"Run ID: {run}\n"
            f"状态: {recovery}\n"
            f"下一步: {next_step}\n"
            f"错误: {self}"
        )


class ArtifactValidationError(CoductorError):
    """Raised when artifact validation or lineage checks fail."""


class PlanValidationError(CoductorError):
    """Raised when a generated execution plan is invalid."""


class BackendUnavailableError(CoductorError):
    """Raised when a requested coding backend cannot be used."""
