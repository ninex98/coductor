from __future__ import annotations

import sqlite3

import pytest

from coductor.workflow.langgraph_checkpoint import (
    LangGraphSqliteCheckpointUnavailable,
    create_langgraph_sqlite_saver,
    langgraph_thread_config,
)


def test_langgraph_thread_config_uses_run_id_as_thread_id() -> None:
    assert langgraph_thread_config("run_abc") == {"configurable": {"thread_id": "run_abc"}}


def test_create_langgraph_sqlite_saver_reports_missing_dependency() -> None:
    connection = sqlite3.connect(":memory:")

    with pytest.raises(LangGraphSqliteCheckpointUnavailable) as exc_info:
        create_langgraph_sqlite_saver(connection)

    assert "langgraph-checkpoint-sqlite" in str(exc_info.value)
