from __future__ import annotations

import sys
from pathlib import Path

from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import RunStatus, WorkerStatus
from coductor.services.run_service import RunService
from coductor.workflow.graph_runner import WorkflowGraphRunner


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


class FailingBackend:
    def start_worker(self, request: WorkerRequest) -> WorkerHandle:
        return WorkerHandle(worker_id=request.worker_id, thread_id="thread_failed")

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            thread_id=handle.thread_id,
            summary="upstream 502",
            exit_reason="failed",
        )

    def cancel_worker(self, handle: WorkerHandle) -> None:
        return None

    def get_status(self, handle: WorkerHandle) -> WorkerStatus:
        return WorkerStatus.FAILED


def test_run_requires_human_when_worker_fails_even_without_gates(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []

    result = RunService(tmp_path, config, backend=FailingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.HUMAN_REQUIRED
    assert result.message == "worker failed: T001"
    run_dir = tmp_path / ".coductor" / "runs" / result.run_id
    assert (run_dir / "tasks" / "T001" / "worker_result.yaml").exists()
    assert not (run_dir / "07_evidence.yaml").exists()


def test_run_service_uses_workflow_graph_runner_for_front_half(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    calls: list[str] = []
    original = WorkflowGraphRunner.run_front_half

    def recording_run_front_half(self, state, *, requested_mode):
        calls.append(state.run_id)
        return original(self, state, requested_mode=requested_mode)

    monkeypatch.setattr(WorkflowGraphRunner, "run_front_half", recording_run_front_half)

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert calls == [result.run_id]


def test_run_service_uses_workflow_graph_runner_for_task_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    calls: list[str] = []
    original = WorkflowGraphRunner.run_task_execution

    def recording_run_task_execution(self, state, *, plan, tasks, on_dispatch=None):
        calls.append(state.run_id)
        return original(self, state, plan=plan, tasks=tasks, on_dispatch=on_dispatch)

    monkeypatch.setattr(
        WorkflowGraphRunner,
        "run_task_execution",
        recording_run_task_execution,
    )

    result = RunService(tmp_path, config, backend=FakeCodingBackend()).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert calls == [result.run_id]


def test_run_service_reports_dispatch_progress_from_task_runner(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = []
    events: list[tuple[str, str]] = []

    result = RunService(
        tmp_path,
        config,
        backend=FakeCodingBackend(),
        progress=lambda stage, message: events.append((stage, message)),
    ).run("创建网页小游戏")

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    assert ("dispatch_tasks", "dispatch T001") in events
