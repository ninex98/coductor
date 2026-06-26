from __future__ import annotations

from coductor.artifacts.models import (
    FileReference,
    GateReportData,
    Producer,
    WorkerResultData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ExecutionStrategy, ProducerKind
from coductor.services.review_delivery_service import ReviewDeliveryService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


def test_review_delivery_service_writes_review_evidence_and_report(tmp_path):
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("# patch\n", encoding="utf-8")
    goal = writer.write_goal(repo, "run_abc", "修复示例函数", requested_mode="auto")
    gate_report = writer.envelope(
        run_id="run_abc",
        artifact_type=ArtifactType.GATE_REPORT,
        artifact_id_prefix="art_gates",
        status=ArtifactStatus.PASSED,
        producer=Producer(kind=ProducerKind.TOOL, name="gate-runner"),
        data=GateReportData(
            base_commit="base",
            head_commit="head",
            gates=[],
            required_gates_passed=True,
            next_action="review",
        ),
    )
    repo.write("05_gate_report.yaml", gate_report)
    worker_result = writer.envelope(
        run_id="run_abc",
        artifact_type=ArtifactType.WORKER_RESULT,
        artifact_id_prefix="art_worker_result",
        status=ArtifactStatus.COMPLETED,
        producer=Producer(kind=ProducerKind.MODEL, name="codex-worker"),
        data=WorkerResultData(
            worker_id="worker_T001",
            thread_id="thread_builder",
            task_id="T001",
            summary="done",
            patch=FileReference(path="tasks/T001/patch.diff", sha256="abc", bytes=8),
        ),
    )
    repo.write("tasks/T001/worker_result.yaml", worker_result)
    service = ReviewDeliveryService(tmp_path, config, FakeCodingBackend(), writer)

    review = service.review(repo, "run_abc", gate_report, ["T001"])
    evidence = service.evidence(
        repo,
        "run_abc",
        goal,
        gate_report,
        review,
        ExecutionStrategy.SOLO,
        ["T001"],
    )

    assert review.data.verdict == "pass"
    assert evidence.data.final_status == "ready_for_human_review"
    assert (tmp_path / "06_review.yaml").exists()
    assert (tmp_path / "07_evidence.yaml").exists()
    assert (tmp_path / "delivery-report.md").exists()
