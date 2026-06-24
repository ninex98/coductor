from __future__ import annotations

import sys
from pathlib import Path

from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus
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


def test_resume_stops_when_existing_artifact_lineage_is_stale(tmp_path: Path) -> None:
    service = RunService(tmp_path, _passing_config(), backend=FakeCodingBackend())
    first = service.run("实现可审计工件链路")
    goal_path = Path(first.run_dir) / "00_goal.yaml"
    goal_path.write_text(
        goal_path.read_text(encoding="utf-8").replace("实现可审计工件链路", "篡改目标"),
        encoding="utf-8",
    )

    resumed = service.resume(first.run_id)

    assert resumed.status == RunStatus.HUMAN_REQUIRED
    assert "stale artifact lineage" in resumed.message
    checkpoint = service.checkpoints.load(first.run_id)
    assert checkpoint is not None
    assert checkpoint.stale_artifacts
