from __future__ import annotations

import sqlite3

import pytest

from coductor.workflow.langgraph_checkpoint import (
    LangGraphSqliteCheckpointUnavailable,
    create_langgraph_sqlite_saver,
    is_langgraph_sqlite_saver_available,
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


def test_real_langgraph_sqlite_saver_smoke_when_dependency_available() -> None:
    if not is_langgraph_sqlite_saver_available():
        pytest.skip("langgraph-checkpoint-sqlite is not installed in this environment")

    connection = sqlite3.connect(":memory:")
    saver = create_langgraph_sqlite_saver(connection)

    assert saver is not None
