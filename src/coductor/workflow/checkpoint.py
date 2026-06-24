"""SQLite workflow checkpoint helpers."""

from __future__ import annotations

from pathlib import Path

from coductor.storage.database import Database
from coductor.workflow.state import WorkflowState


class WorkflowCheckpointStore:
    def __init__(self, database: Database, runs_dir: Path) -> None:
        self.database = database
        self.runs_dir = runs_dir

    def save(self, state: WorkflowState, updated_at: str) -> None:
        run_dir = state.run_dir or (self.runs_dir / state.run_id).as_posix()
        state.updated_at = updated_at
        self.database.save_checkpoint(
            state.run_id,
            state.model_dump_json(),
            updated_at,
            run_dir=run_dir,
            status=str(state.status),
        )

    def load(self, run_id: str) -> WorkflowState | None:
        data = self.database.get_checkpoint(run_id)
        if data is None:
            return None
        return WorkflowState.model_validate(data)
