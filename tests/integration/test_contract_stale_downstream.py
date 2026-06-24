from __future__ import annotations

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


def test_downstream_task_becomes_stale_when_contract_hash_changes(tmp_path: Path) -> None:
    service = RunService(tmp_path, _passing_config(), backend=FakeCodingBackend())
    first = service.run(
        "先定义 JSON Schema，再让 CLI 输出符合该 Schema",
        mode=ExecutionMode.AUTO,
    )
    contract_path = Path(first.run_dir) / "contracts/generated.schema.json"
    contract_path.write_text('{"type":"array"}', encoding="utf-8")

    resumed = service.resume(first.run_id)

    assert resumed.status == RunStatus.HUMAN_REQUIRED
    assert "stale" in resumed.message
    checkpoint = service.checkpoints.load(first.run_id)
    assert checkpoint is not None
    assert any("contracts/generated.schema.json" in item for item in checkpoint.stale_artifacts)
