from __future__ import annotations

from coductor.artifacts.models import (
    FileReference,
    GateReportData,
    Producer,
    WorkerResultData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import BackendUsage, WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ExecutionStrategy, ProducerKind
from coductor.services.review_delivery_service import ReviewDeliveryService
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class TextReviewBackend(FakeCodingBackend):
    def __init__(self, review_summary: str) -> None:
        super().__init__()
        self.review_summary = review_summary

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        if request.role == "reviewer":
            return WorkerResult(
                worker_id=request.worker_id,
                thread_id=handle.thread_id,
                summary=self.review_summary,
                usage=BackendUsage(input_tokens=30, output_tokens=6, estimated=False),
            )
        return super().continue_worker(handle, request)


def test_review_delivery_service_writes_review_evidence_and_report(tmp_path):
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/math_utils.py b/math_utils.py\n", encoding="utf-8")
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
    service = ReviewDeliveryService(tmp_path, config, TextReviewBackend("VERDICT: pass"), writer)

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
    assert review.data.usage.input_tokens == 30
    assert review.data.usage.output_tokens == 6
    assert review.data.usage.total_tokens == 36
    assert review.data.usage.estimated is False
    assert evidence.data.final_status == "ready_for_human_review"
    assert (tmp_path / "06_review.yaml").exists()
    assert (tmp_path / "07_evidence.yaml").exists()
    assert (tmp_path / "delivery-report.md").exists()


def test_review_delivery_service_parses_blocking_reviewer_output(tmp_path):
    config = CoductorConfig.default()
    repo = ArtifactRepository(tmp_path)
    writer = WorkflowArtifactWriter(tmp_path, config)
    patch = tmp_path / "tasks/T001/patch.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/src/app.py b/src/app.py\n", encoding="utf-8")
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
    backend = TextReviewBackend(
        "\n".join(
            [
                "VERDICT: fail",
                "BLOCKING: true",
                "FINDING: severity=critical; category=correctness; "
                "file=src/app.py; line=42; description=状态判断会误报通过; "
                "recommendation=修复状态判断后重新验证",
            ]
        )
    )
    service = ReviewDeliveryService(tmp_path, config, backend, writer)

    review = service.review(repo, "run_abc", gate_report, ["T001"])

    assert review.status == "failed"
    assert review.data.verdict == "fail"
    assert review.data.requires_repair is True
    assert review.data.blocking_findings == 1
    assert review.data.findings[0].severity == "critical"
    assert review.data.findings[0].file == "src/app.py"
    assert review.data.findings[0].line == 42
