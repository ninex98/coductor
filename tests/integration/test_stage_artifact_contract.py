from __future__ import annotations

import sys
from pathlib import Path

from coductor.artifacts.serializer import load_yaml
from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus, WorkerStatus
from coductor.services.run_service import RunService
from coductor.workflow.stage_artifacts import SUCCESS_STAGE_ARTIFACTS

REQUIRED_SUCCESS_ARTIFACTS = {
    artifact.path_template.format(task_id="T001"): artifact.artifact_type
    for artifact in SUCCESS_STAGE_ARTIFACTS
}


def test_successful_run_writes_fixed_yaml_artifacts(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("修复示例函数")
    run_dir = Path(result.run_dir)

    for relative_path, artifact_type in REQUIRED_SUCCESS_ARTIFACTS.items():
        artifact_path = run_dir / relative_path
        assert artifact_path.exists(), relative_path
        artifact = load_yaml(artifact_path.read_text(encoding="utf-8"))
        assert artifact["schema_version"] == "1.0"
        assert artifact["artifact_type"] == artifact_type
        assert artifact["run_id"] == result.run_id

    assert (run_dir / "delivery-report.md").exists()


def test_repair_run_writes_fixed_repair_yaml_artifacts(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.workflow.max_repair_attempts = 2
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            command=(
                f'{sys.executable} -c "from pathlib import Path; import sys; '
                f"p=Path({str(marker)!r}); "
                'sys.exit(0 if p.exists() else 1)"'
            ),
            required=True,
            timeout_seconds=30,
        )
    ]
    backend = FakeCodingBackend(
        repair_side_effect=lambda: marker.write_text("fixed", encoding="utf-8")
    )

    result = RunService(tmp_path, config, backend=backend).run("修复失败测试")
    run_dir = Path(result.run_dir)

    repair_artifacts = {
        "repairs/R001/repair_request.yaml": "repair_request",
        "repairs/R001/repair_result.yaml": "repair_result",
        "05_gate_report.yaml": "gate_report",
        "07_evidence.yaml": "evidence_bundle",
    }
    for relative_path, artifact_type in repair_artifacts.items():
        artifact = load_yaml((run_dir / relative_path).read_text(encoding="utf-8"))
        assert artifact["artifact_type"] == artifact_type
        assert artifact["run_id"] == result.run_id


class ContractFailingBackend:
    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        return WorkerHandle(worker_id=request.worker_id, thread_id="thread_failed")

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="backend failed before completing task",
            exit_reason="failed",
        )

    def cancel_worker(self, handle: WorkerHandle) -> None:
        return None

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.FAILED


def test_worker_failure_writes_failure_artifacts_without_downstream_evidence(
    tmp_path: Path,
) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []

    result = RunService(tmp_path, config, backend=ContractFailingBackend()).run("实现功能")
    run_dir = Path(result.run_dir)

    assert result.status == RunStatus.HUMAN_REQUIRED
    worker_result = load_yaml(
        (run_dir / "tasks/T001/worker_result.yaml").read_text(encoding="utf-8")
    )
    assert worker_result["artifact_type"] == "worker_result"
    assert worker_result["data"]["exit_reason"] == "failed"
    assert not (run_dir / "04_integration.yaml").exists()
    assert not (run_dir / "06_review.yaml").exists()
    assert not (run_dir / "07_evidence.yaml").exists()
