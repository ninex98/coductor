"""LangGraph SQLite checkpoint adapter boundary."""

from __future__ import annotations

import sqlite3
from typing import Any


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
