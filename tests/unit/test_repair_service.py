from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import GateReportData, GateResultData, Producer, TaskData
from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import load_yaml
from coductor.backends.base import BackendUsage, WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ProducerKind
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


class FileChangingRepairBackend(FakeCodingBackend):
    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        target = Path(request.workspace_path) / "math_utils.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="repair changed math_utils.py",
            files_changed=["math_utils.py"],
        )


def _write_gate_report(
    repo: ArtifactRepository,
    writer: WorkflowArtifactWriter,
) -> GateReportData:
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
    return gate_report


def test_repair_service_writes_repair_request_and_result(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    gate_report = _write_gate_report(repo, writer)
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


def test_repair_request_inherits_target_task_path_boundaries(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    gate_report = _write_gate_report(repo, writer)
    task = writer.envelope(
        run_id="run_abc",
        artifact_type=ArtifactType.TASK,
        artifact_id_prefix="art_task",
        status=ArtifactStatus.READY,
        producer=Producer(kind=ProducerKind.SYSTEM, name="test"),
        data=TaskData(
            task_id="T001",
            objective="更新文档",
            role="builder",
            allowed_paths=["docs/**"],
            forbidden_paths=["docs/private/**"],
        ),
    )
    repo.write("tasks/T001/task.yaml", task)
    service = RepairService(tmp_path, config, UsageRepairBackend(), writer)

    service.repair(
        repo,
        "run_abc",
        WorkerHandle(worker_id="worker_T001", thread_id="thread_builder"),
        gate_report,
        attempt=1,
        target_task_id="T001",
    )

    repair_request = load_yaml(
        (tmp_path / "repairs/R001/repair_request.yaml").read_text(encoding="utf-8")
    )
    assert repair_request["data"]["allowed_paths"] == ["docs/**"]
    assert repair_request["data"]["forbidden_paths"] == ["docs/private/**"]


def test_repair_service_captures_real_patch_diff(tmp_path: Path) -> None:
    (tmp_path / "math_utils.py").write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path / ".coductor" / "runs" / "run_abc")
    writer = WorkflowArtifactWriter(tmp_path, config)
    gate_report = _write_gate_report(repo, writer)
    service = RepairService(tmp_path, config, FileChangingRepairBackend(), writer)

    service.repair(
        repo,
        "run_abc",
        WorkerHandle(worker_id="worker_T001", thread_id="thread_builder"),
        gate_report,
        attempt=1,
        target_task_id="T001",
    )

    patch = (repo.root / "repairs/R001/repair_result.patch").read_text(encoding="utf-8")
    assert "fake repair result" not in patch
    assert "diff --git a/math_utils.py b/math_utils.py" in patch
    assert "-    return 0" in patch
    assert "+    return a + b" in patch


def test_repair_request_does_not_claim_thread_resume_when_backend_cannot_resume(
    tmp_path: Path,
) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "codex_exec"
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    gate_report = _write_gate_report(repo, writer)
    service = RepairService(tmp_path, config, UsageRepairBackend(), writer)

    service.repair(
        repo,
        "run_abc",
        WorkerHandle(worker_id="worker_T001", thread_id="thread_builder"),
        gate_report,
        attempt=1,
        target_task_id="T001",
    )

    repair_request = load_yaml(
        (tmp_path / "repairs/R001/repair_request.yaml").read_text(encoding="utf-8")
    )

    assert repair_request["data"]["resume_thread_id"] is None
