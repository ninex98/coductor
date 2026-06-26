"""LangGraph SQLite checkpoint adapter boundary."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from coductor.workflow.graph import compile_workflow_graph
from coductor.workflow.state import WorkflowState


class LangGraphSqliteCheckpointUnavailable(RuntimeError):
    """Raised when the optional LangGraph SQLite saver package is unavailable."""


def langgraph_thread_config(run_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": run_id}}


def _load_sqlite_saver() -> Any:
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver


def is_langgraph_sqlite_saver_available() -> bool:
    try:
        _load_sqlite_saver()
    except ModuleNotFoundError:
        return False
    return True


def create_langgraph_sqlite_saver(connection: sqlite3.Connection) -> Any:
    try:
        sqlite_saver = _load_sqlite_saver()
    except ModuleNotFoundError as exc:
        raise LangGraphSqliteCheckpointUnavailable(
            "LangGraph SQLite checkpointing requires langgraph-checkpoint-sqlite."
        ) from exc
    return sqlite_saver(connection)


class LangGraphCheckpointStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def save(self, state: WorkflowState) -> None:
        graph, connection = self._compile_graph()
        if graph is None:
            return
        try:
            graph.update_state(
                langgraph_thread_config(state.run_id),
                state.model_dump(mode="json"),
            )
        finally:
            connection.close()

    def load(self, run_id: str) -> WorkflowState | None:
        graph, connection = self._compile_graph()
        if graph is None:
            return None
        try:
            snapshot = graph.get_state(langgraph_thread_config(run_id))
        finally:
            connection.close()
        if not snapshot.values:
            return None
        return WorkflowState.model_validate(snapshot.values)

    def checkpointer(self) -> Any | None:
        connection = sqlite3.connect(self.database_path)
        try:
            return create_langgraph_sqlite_saver(connection)
        except LangGraphSqliteCheckpointUnavailable:
            connection.close()
            return None

    def compile_graph(self) -> Any:
        return compile_workflow_graph(checkpointer=self.checkpointer())

    def _compile_graph(self) -> tuple[Any | None, sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        try:
            saver = create_langgraph_sqlite_saver(connection)
        except LangGraphSqliteCheckpointUnavailable:
            connection.close()
            return None, connection
        return compile_workflow_graph(checkpointer=saver), connection
