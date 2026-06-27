from __future__ import annotations

from coductor.artifacts.models import GateReportData, GateResultData
from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import load_yaml
from coductor.backends.base import BackendUsage, WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType
from coductor.services.repair_service import RepairService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class UsageRepairBackend(FakeCodingBackend):
    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="repair complete",
            usage=BackendUsage(input_tokens=20, output_tokens=4, estimated=False),
        )


def test_repair_service_writes_repair_request_and_result(tmp_path):
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    gate_report = writer.envelope(
        run_id="run_abc",
        artifact_type=ArtifactType.GATE_REPORT,
        artifact_id_prefix="art_gates",
        status=ArtifactStatus.FAILED,
        producer={"kind": "tool", "name": "gate-runner"},
        data=GateReportData(
            base_commit="base",
            head_commit="head",
            gates=[
                GateResultData(
                    id="unit_tests",
                    required=True,
                    status="failed",
                    command="pytest",
                    exit_code=1,
                    duration_ms=10,
                    stdout_path="logs/unit.stdout.log",
                    stderr_path="logs/unit.stderr.log",
                    failure_fingerprint="abc",
                )
            ],
            required_gates_passed=False,
            next_action="repair",
        ),
    )
    repo.write("05_gate_report.yaml", gate_report)
    service = RepairService(tmp_path, config, UsageRepairBackend(), writer)

    service.repair(
        repo,
        "run_abc",
        WorkerHandle(worker_id="worker_T001", thread_id="thread_builder"),
        gate_report,
        attempt=1,
        target_task_id="T001",
    )

    assert (tmp_path / "repairs/R001/repair_request.yaml").exists()
    assert (tmp_path / "repairs/R001/repair_result.yaml").exists()
    repair_result = load_yaml(
        (tmp_path / "repairs/R001/repair_result.yaml").read_text(encoding="utf-8")
    )
    assert repair_result["data"]["usage"]["input_tokens"] == 20
    assert repair_result["data"]["usage"]["output_tokens"] == 4
    assert repair_result["data"]["usage"]["total_tokens"] == 24
    assert repair_result["data"]["usage"]["estimated"] is False
