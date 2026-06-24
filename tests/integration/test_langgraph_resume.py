from __future__ import annotations

import sys
from pathlib import Path

from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus
from coductor.services.run_service import RunService
from coductor.workflow.state import WorkflowState


def _config(command: str) -> CoductorConfig:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.workflow.max_repair_attempts = 2
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            command=command,
            required=True,
            timeout_seconds=30,
        )
    ]
    return config


def test_resume_continues_existing_run_id_from_persisted_state(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    command = (
        f'{sys.executable} -c "from pathlib import Path; import sys; '
        f"p=Path({str(marker)!r}); "
        'sys.exit(0 if p.exists() else 1)"'
    )
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )
    service = RunService(tmp_path, _config(command), backend=backend)
    run_id = "run_resume_0000000000000000000001"
    run_dir = tmp_path / ".coductor" / "runs" / run_id
    run_dir.mkdir(parents=True)
    service.save_checkpoint(
        WorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            current_stage="run_quality_gates",
            repair_attempts=0,
            raw_goal="修复示例函数并补充测试",
            requested_mode="auto",
        )
    )

    result = service.resume(run_id)

    assert result.run_id == run_id
    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result.repair_attempts == 1
    assert (run_dir / "07_evidence.yaml").exists()


def test_resume_rejects_unknown_run_id(tmp_path: Path) -> None:
    service = RunService(tmp_path, CoductorConfig.default(), backend=FakeCodingBackend())

    result = service.resume("run_missing")

    assert result.status == RunStatus.HUMAN_REQUIRED
    assert "unknown run" in result.message
