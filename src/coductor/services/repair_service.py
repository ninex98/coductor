"""Failure repair request/result artifact handling."""

from __future__ import annotations

import time
from pathlib import Path

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    FileReference,
    GateReportData,
    Producer,
    RepairRequestData,
    WorkerResultData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.backends.base import CodingBackend, WorkerHandle, WorkerRequest
from coductor.backends.capabilities import describe_backend_capability
from coductor.backends.factory import is_codex_sdk_available
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ProducerKind, SandboxMode
from coductor.prompts.renderer import render_worker_prompt
from coductor.services.task_execution_service import TaskExecutionService
from coductor.services.usage import usage_from_backend
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class RepairService:
    def __init__(
        self,
        root: Path,
        config: CoductorConfig,
        backend: CodingBackend,
        artifacts: WorkflowArtifactWriter,
    ) -> None:
        self.root = root
        self.config = config
        self.backend = backend
        self.artifacts = artifacts

    def repair(
        self,
        repo: ArtifactRepository,
        run_id: str,
        builder_handle: WorkerHandle,
        gate_report: ArtifactEnvelope[GateReportData],
        attempt: int,
        target_task_id: str,
    ) -> None:
        failed = [gate.id for gate in gate_report.data.gates if gate.status != "passed"]
        fingerprints = [
            gate.failure_fingerprint for gate in gate_report.data.gates if gate.failure_fingerprint
        ]
        repair_id = f"R{attempt:03d}"
        repair_dir = f"repairs/{repair_id}"
        can_resume_thread = describe_backend_capability(
            self.config.backend.provider,
            sdk_available=is_codex_sdk_available(),
        ).supports_resume_thread
        resume_thread_id = builder_handle.thread_id if can_resume_thread else None
        request_data = RepairRequestData(
            repair_id=repair_id,
            target_task_id=target_task_id,
            resume_thread_id=resume_thread_id,
            attempt=attempt,
            max_attempts=self.config.workflow.max_repair_attempts,
            failed_gates=failed,
            failure_fingerprints=[fp for fp in fingerprints if fp],
            evidence_paths=["05_gate_report.yaml"],
            allowed_paths=["src/**", "tests/**"],
        )
        request_envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPAIR_REQUEST,
            artifact_id_prefix="art_repair_req",
            status=ArtifactStatus.READY,
            producer=Producer(kind=ProducerKind.SYSTEM, name="repair-planner"),
            data=request_data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for("05_gate_report.yaml", gate_report)
                )
            ],
        )
        repo.write(f"{repair_dir}/repair_request.yaml", request_envelope)
        request = WorkerRequest(
            worker_id=f"worker_{target_task_id}_repair",
            role="repairer",
            prompt=render_worker_prompt(
                "repairer",
                ["05_gate_report.yaml"],
                request_data.instruction,
            ),
            workspace_path=self.root.as_posix(),
            sandbox=SandboxMode.WORKSPACE_WRITE,
            thread_policy="resume" if can_resume_thread else "new",
            existing_thread_id=resume_thread_id,
        )
        diff_helper = TaskExecutionService(self.root, self.config, self.backend, self.artifacts)
        before_snapshot = diff_helper.workspace_snapshot(self.root)
        started_at = time.monotonic()
        result = self.backend.continue_worker(builder_handle, request)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        patch = repo.root / f"{repair_dir}/repair_result.patch"
        diff = diff_helper.workspace_diff(self.root)
        if not diff.strip():
            diff = diff_helper.snapshot_diff(
                before_snapshot,
                diff_helper.workspace_snapshot(self.root),
            )
        if diff.strip():
            patch.write_text(diff, encoding="utf-8")
        else:
            patch.write_text("# coductor no repair diff captured\n", encoding="utf-8")
        usage = usage_from_backend(
            result.usage,
            prompt=request.prompt,
            summary=result.summary,
            duration_ms=duration_ms,
        )
        result_data = WorkerResultData(
            worker_id=result.worker_id,
            thread_id=result.thread_id,
            task_id=target_task_id,
            summary=result.summary,
            patch=FileReference(
                path=f"{repair_dir}/repair_result.patch",
                sha256=file_sha256(patch),
                bytes=patch.stat().st_size,
            ),
            usage=usage,
            exit_reason=result.exit_reason,
        )
        result_envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPAIR_RESULT,
            artifact_id_prefix="art_repair_result",
            status=ArtifactStatus.COMPLETED,
            producer=Producer(kind=ProducerKind.MODEL, name="repair-worker"),
            data=result_data,
            inputs=[
                ArtifactInput.model_validate(
                    repo.input_for(f"{repair_dir}/repair_request.yaml", request_envelope)
                )
            ],
        )
        repo.write(f"{repair_dir}/repair_result.yaml", result_envelope)
