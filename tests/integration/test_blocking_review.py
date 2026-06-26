from __future__ import annotations

import sys
from pathlib import Path

from coductor.artifacts.serializer import load_yaml
from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
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


class BlockingReviewBackend(FakeCodingBackend):
    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        if request.role == "reviewer":
            return WorkerResult(
                worker_id=request.worker_id,
                thread_id=handle.thread_id,
                summary=(
                    "VERDICT: fail\n"
                    "BLOCKING: true\n"
                    "FINDING: severity=critical; category=correctness; "
                    "description=阻塞问题; recommendation=修复后重新 review"
                ),
            )
        return super().continue_worker(handle, request)


def test_blocking_review_still_writes_human_required_evidence(
    tmp_path: Path,
) -> None:
    result = RunService(
        tmp_path,
        _passing_config(),
        backend=BlockingReviewBackend(),
    ).run("修复示例函数并补充测试")

    run_dir = Path(result.run_dir)
    evidence = load_yaml((run_dir / "07_evidence.yaml").read_text())
    report = (run_dir / "delivery-report.md").read_text(encoding="utf-8")
    assert result.status == RunStatus.HUMAN_REQUIRED
    assert evidence["status"] == "human_required"
    assert evidence["data"]["final_status"] == "human_required"
    assert evidence["data"]["review_summary"]["blocking_findings"] == 1
    assert "Final status: human_required" in report
