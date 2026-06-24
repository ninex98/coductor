from __future__ import annotations

import sys
from pathlib import Path

from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus
from coductor.services.run_service import RunService


def _config(command: str, *, max_repair_attempts: int = 2) -> CoductorConfig:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.workflow.max_repair_attempts = max_repair_attempts
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            stage="final",
            command=command,
            required=True,
            timeout_seconds=30,
        )
    ]
    return config


def test_fake_backend_run_repairs_after_initial_gate_failure(tmp_path: Path) -> None:
    marker = tmp_path / "repair-marker"
    command = (
        f'{sys.executable} -c "from pathlib import Path; import sys; '
        f"p=Path({str(marker)!r}); "
        'sys.exit(0 if p.exists() else 1)"'
    )
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )

    result = RunService(tmp_path, _config(command), backend=backend).run(
        "修复示例函数并补充测试"
    )

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert result.repair_attempts == 1
    assert (tmp_path / ".coductor" / "runs" / result.run_id / "07_evidence.yaml").exists()
    assert (tmp_path / ".coductor" / "runs" / result.run_id / "delivery-report.md").exists()
    assert backend.review_thread_ids != backend.builder_thread_ids


def test_run_stops_at_max_repair_attempts(tmp_path: Path) -> None:
    command = f"{sys.executable} -c 'import sys; sys.exit(1)'"

    result = RunService(
        tmp_path,
        _config(command, max_repair_attempts=1),
        backend=FakeCodingBackend(),
    ).run("修复示例函数并补充测试")

    assert result.status == RunStatus.HUMAN_REQUIRED
    assert result.repair_attempts == 1
    assert (tmp_path / ".coductor" / "runs" / result.run_id / "05_gate_report.yaml").exists()
