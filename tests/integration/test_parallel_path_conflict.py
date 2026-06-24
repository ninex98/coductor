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


def test_parallel_plan_with_overlapping_paths_is_human_required(
    tmp_path: Path,
) -> None:
    result = RunService(
        tmp_path,
        _passing_config(),
        backend=FakeCodingBackend(),
    ).run(
        "并行修改核心 src 和 coductor 子模块",
        mode=ExecutionMode.PARALLEL,
    )

    assert result.status == RunStatus.HUMAN_REQUIRED
    assert "parallel path overlap" in result.message
    run_dir = Path(result.run_dir)
    assert (run_dir / "03_execution_plan.yaml").exists()
    assert not (run_dir / "tasks/T001/task.yaml").exists()
