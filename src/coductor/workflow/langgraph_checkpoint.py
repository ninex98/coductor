"""LangGraph SQLite checkpoint adapter boundary."""

from __future__ import annotations

import sqlite3
from typing import Any


class LangGraphSqliteCheckpointUnavailable(RuntimeError):
    """Raised when the optional LangGraph SQLite saver package is unavailable."""


def langgraph_thread_config(run_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": run_id}}


def create_langgraph_sqlite_saver(connection: sqlite3.Connection) -> Any:
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise LangGraphSqliteCheckpointUnavailable(
            "LangGraph SQLite checkpointing requires langgraph-checkpoint-sqlite."
        ) from exc
    return SqliteSaver(connection)
