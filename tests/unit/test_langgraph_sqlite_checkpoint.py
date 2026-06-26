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


def test_create_langgraph_sqlite_saver_reports_missing_dependency(monkeypatch) -> None:
    connection = sqlite3.connect(":memory:")

    def missing_importer():
        raise ModuleNotFoundError("missing")

    monkeypatch.setattr(
        "coductor.workflow.langgraph_checkpoint._load_sqlite_saver",
        missing_importer,
    )

    with pytest.raises(LangGraphSqliteCheckpointUnavailable) as exc_info:
        create_langgraph_sqlite_saver(connection)

    assert "langgraph-checkpoint-sqlite" in str(exc_info.value)


def test_create_langgraph_sqlite_saver_uses_available_dependency(monkeypatch) -> None:
    connection = sqlite3.connect(":memory:")
    calls: list[sqlite3.Connection] = []

    class FakeSqliteSaver:
        def __init__(self, received: sqlite3.Connection) -> None:
            calls.append(received)

    monkeypatch.setattr(
        "coductor.workflow.langgraph_checkpoint._load_sqlite_saver",
        lambda: FakeSqliteSaver,
    )

    saver = create_langgraph_sqlite_saver(connection)

    assert isinstance(saver, FakeSqliteSaver)
    assert calls == [connection]
