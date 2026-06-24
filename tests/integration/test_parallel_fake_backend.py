from __future__ import annotations

import sys
from pathlib import Path

from coductor.artifacts.serializer import load_yaml
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


def test_parallel_fake_backend_merges_safe_tasks(tmp_path: Path) -> None:
    result = RunService(
        tmp_path,
        _passing_config(),
        backend=FakeCodingBackend(),
    ).run(
        "并行更新文档和示例",
        mode=ExecutionMode.PARALLEL,
    )

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    run_dir = Path(result.run_dir)
    integration = load_yaml((run_dir / "04_integration.yaml").read_text())
    assert integration["data"]["status"] == "merged"
    assert integration["data"]["merged_tasks"] == ["T001", "T002"]
    assert integration["data"]["conflicts"] == []
    assert (run_dir / "tasks/T001/task.yaml").exists()
    assert (run_dir / "tasks/T002/task.yaml").exists()
