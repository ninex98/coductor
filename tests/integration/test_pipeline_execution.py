from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import ExecutionMode, RunStatus
from coductor.services.run_service import RunService


def _passing_config() -> CoductorConfig:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            stage="final",
            command=f"{sys.executable} -c 'print(1)'",
            required=True,
            timeout_seconds=30,
        )
    ]
    return config


def _events(root: Path, run_id: str) -> list[str]:
    db_path = root / ".coductor" / "coductor.sqlite3"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "select message from events where run_id = ? order by id",
            (run_id,),
        ).fetchall()
    return [row[0] for row in rows]


def test_pipeline_executes_tasks_in_dependency_order(tmp_path: Path) -> None:
    result = RunService(
        tmp_path,
        _passing_config(),
        backend=FakeCodingBackend(),
    ).run(
        "先定义 JSON Schema，再让 CLI 输出符合该 Schema",
        mode=ExecutionMode.AUTO,
    )

    events = _events(tmp_path, result.run_id)

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert events.index("dispatch T001") < events.index("dispatch T002")
    run_dir = Path(result.run_dir)
    assert (run_dir / "tasks/T001/task.yaml").exists()
    assert (run_dir / "tasks/T002/task.yaml").exists()
