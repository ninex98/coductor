"""SQLite storage with SQLAlchemy fallback-free implementation."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists runs (
                    run_id text primary key,
                    status text not null,
                    run_dir text not null,
                    updated_at text not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists events (
                    id integer primary key autoincrement,
                    run_id text not null,
                    stage text not null,
                    message text not null,
                    created_at text not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists workflow_checkpoints (
                    run_id text primary key,
                    state_json text not null,
                    updated_at text not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists run_locks (
                    run_id text primary key,
                    owner text not null,
                    acquired_at text not null default current_timestamp
                )
                """
            )

    def upsert_run(self, run_id: str, status: str, run_dir: str, updated_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into runs(run_id, status, run_dir, updated_at)
                values (?, ?, ?, ?)
                on conflict(run_id) do update set
                    status=excluded.status,
                    run_dir=excluded.run_dir,
                    updated_at=excluded.updated_at
                """,
                (run_id, status, run_dir, updated_at),
            )

    def get_run(self, run_id: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "select run_id, status, run_dir, updated_at from runs where run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {"run_id": row[0], "status": row[1], "run_dir": row[2], "updated_at": row[3]}

    def update_run_status(self, run_id: str, status: str, updated_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                update runs
                set status = ?, updated_at = ?
                where run_id = ?
                """,
                (status, updated_at, run_id),
            )

    def latest_run(self) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                select run_id, status, run_dir, updated_at
                from runs
                order by updated_at desc
                limit 1
                """
            ).fetchone()
        if row is None:
            return None
        return {"run_id": row[0], "status": row[1], "run_dir": row[2], "updated_at": row[3]}

    def list_runs(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, str]]:
        normalized_limit = max(1, min(limit, 500))
        with self._connect() as conn:
            if status is None:
                rows = conn.execute(
                    """
                    select run_id, status, run_dir, updated_at
                    from runs
                    order by updated_at desc
                    limit ?
                    """,
                    (normalized_limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    select run_id, status, run_dir, updated_at
                    from runs
                    where status = ?
                    order by updated_at desc
                    limit ?
                    """,
                    (status, normalized_limit),
                ).fetchall()
        return [
            {
                "run_id": row[0],
                "status": row[1],
                "run_dir": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def add_event(self, run_id: str, stage: str, message: str, created_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "insert into events(run_id, stage, message, created_at) values (?, ?, ?, ?)",
                (run_id, stage, message, created_at),
            )

    def list_events(self, run_id: str) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select stage, message, created_at
                from events
                where run_id = ?
                order by id
                """,
                (run_id,),
            ).fetchall()
        return [
            {"stage": row[0], "message": row[1], "created_at": row[2]}
            for row in rows
        ]

    def save_checkpoint(
        self,
        run_id: str,
        state_json: str,
        updated_at: str,
        *,
        run_dir: str | None = None,
        status: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into workflow_checkpoints(run_id, state_json, updated_at)
                values (?, ?, ?)
                on conflict(run_id) do update set
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (run_id, state_json, updated_at),
            )
            if run_dir is not None and status is not None:
                conn.execute(
                    """
                    insert into runs(run_id, status, run_dir, updated_at)
                    values (?, ?, ?, ?)
                    on conflict(run_id) do update set
                        status=excluded.status,
                        run_dir=excluded.run_dir,
                        updated_at=excluded.updated_at
                    """,
                    (run_id, status, run_dir, updated_at),
                )

    def get_checkpoint(self, run_id: str) -> Mapping[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "select state_json from workflow_checkpoints where run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        import json

        loaded = json.loads(row[0])
        if not isinstance(loaded, dict):
            raise ValueError(f"checkpoint for {run_id} is not a JSON object")
        return loaded

    def acquire_run_lock(
        self,
        run_id: str,
        owner: str,
        *,
        now: str | None = None,
        acquired_at: str | None = None,
        stale_after_seconds: int | None = None,
    ) -> bool:
        timestamp = acquired_at or now or _utc_now()
        if stale_after_seconds is not None:
            self._release_stale_run_lock(run_id, timestamp, stale_after_seconds)
        try:
            with self._connect() as conn:
                conn.execute(
                    "insert into run_locks(run_id, owner, acquired_at) values (?, ?, ?)",
                    (run_id, owner, timestamp),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def get_run_lock(self, run_id: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "select run_id, owner, acquired_at from run_locks where run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {"run_id": row[0], "owner": row[1], "acquired_at": row[2]}

    def release_run_lock(self, run_id: str, owner: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "delete from run_locks where run_id = ? and owner = ?",
                (run_id, owner),
            )
        return cursor.rowcount == 1

    def _release_stale_run_lock(
        self,
        run_id: str,
        now: str,
        stale_after_seconds: int,
    ) -> None:
        lock = self.get_run_lock(run_id)
        if lock is None:
            return
        elapsed = (_parse_utc(now) - _parse_utc(lock["acquired_at"])).total_seconds()
        if elapsed <= stale_after_seconds:
            return
        with self._connect() as conn:
            conn.execute("delete from run_locks where run_id = ?", (run_id,))


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
