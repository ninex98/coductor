from __future__ import annotations

from coductor.storage.database import Database


def test_database_run_lock_is_exclusive_and_owner_checked(tmp_path) -> None:
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")

    assert db.acquire_run_lock("run_abc", "owner_a") is True
    assert db.acquire_run_lock("run_abc", "owner_b") is False
    assert db.release_run_lock("run_abc", "owner_b") is False
    assert db.acquire_run_lock("run_abc", "owner_b") is False
    assert db.release_run_lock("run_abc", "owner_a") is True
    assert db.acquire_run_lock("run_abc", "owner_b") is True


def test_database_run_lock_can_take_over_stale_owner(tmp_path) -> None:
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")

    assert db.acquire_run_lock(
        "run_abc",
        "owner_a",
        acquired_at="2026-06-24T00:00:00Z",
    )

    assert not db.acquire_run_lock(
        "run_abc",
        "owner_b",
        now="2026-06-24T00:00:30Z",
        stale_after_seconds=60,
    )
    assert db.acquire_run_lock(
        "run_abc",
        "owner_b",
        now="2026-06-24T00:02:01Z",
        stale_after_seconds=60,
    )
    lock = db.get_run_lock("run_abc")
    assert lock == {
        "run_id": "run_abc",
        "owner": "owner_b",
        "acquired_at": "2026-06-24T00:02:01Z",
    }
    assert db.release_run_lock("run_abc", "owner_a") is False
    assert db.release_run_lock("run_abc", "owner_b") is True
