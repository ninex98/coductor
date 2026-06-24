from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coductor.artifacts.models import Finding, Producer, ReviewReportData
from coductor.artifacts.serializer import load_yaml
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import ArtifactType, ProducerKind, RunStatus
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


def test_blocking_review_still_writes_human_required_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def blocking_review(
        self: RunService,
        repo: object,
        run_id: str,
        gate_report: object,
        completed_task_ids: list[str],
    ) -> object:
        del completed_task_ids
        data = ReviewReportData(
            reviewer_thread_id="thread_review",
            reviewed_base_commit=gate_report.data.base_commit,
            reviewed_head_commit=gate_report.data.head_commit,
            findings=[
                Finding(
                    id="F001",
                    severity="critical",
                    category="correctness",
                    description="阻塞问题",
                    recommendation="修复后重新 review",
                )
            ],
            blocking_findings=1,
            verdict="fail",
            requires_repair=True,
        )
        envelope = RunService._envelope(
            self,
            run_id=run_id,
            artifact_type=ArtifactType.REVIEW_REPORT,
            artifact_id_prefix="art_review",
            status="failed",
            producer=Producer(kind=ProducerKind.MODEL, name="independent-reviewer"),
            data=data,
            inputs=[],
        )
        repo.write("06_review.yaml", envelope)
        return envelope

    monkeypatch.setattr(RunService, "_review", blocking_review)

    result = RunService(
        tmp_path,
        _passing_config(),
        backend=FakeCodingBackend(),
    ).run("修复示例函数并补充测试")

    run_dir = Path(result.run_dir)
    evidence = load_yaml((run_dir / "07_evidence.yaml").read_text())
    report = (run_dir / "delivery-report.md").read_text(encoding="utf-8")
    assert result.status == RunStatus.HUMAN_REQUIRED
    assert evidence["status"] == "human_required"
    assert evidence["data"]["final_status"] == "human_required"
    assert evidence["data"]["review_summary"]["blocking_findings"] == 1
    assert "Final status: human_required" in report
