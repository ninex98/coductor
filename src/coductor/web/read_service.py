"""Read-only data facade for the local web console."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import load_yaml
from coductor.constants import CODUCTOR_DIR, VERSION
from coductor.services.report_service import ReportService, RunReportError
from coductor.storage.database import Database
from coductor.web.paths import ConsolePathError, read_text_preview, resolve_run_file
from coductor.web.schemas import (
    ConsoleArtifactDetail,
    ConsoleArtifactSummary,
    ConsoleCheckpointSummary,
    ConsoleEvent,
    ConsoleEvidenceSummary,
    ConsoleHealth,
    ConsoleReleaseSummary,
    ConsoleRunDetail,
    ConsoleRunSummary,
    ConsoleTextFile,
)
from coductor.workflow.state import WorkflowState


class ConsoleReadError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        recoverable: bool = True,
        next_command: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.recoverable = recoverable
        self.next_command = next_command


class ConsoleReadService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.db = Database(root / CODUCTOR_DIR / "coductor.sqlite3")
        self.reports = ReportService(self.db)

    def health(self) -> ConsoleHealth:
        return ConsoleHealth(root=self.root.as_posix(), version=VERSION)

    def list_runs(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ConsoleRunSummary]:
        return [
            self._run_summary(row)
            for row in self.db.list_runs(status=status, limit=limit)
        ]

    def get_run(self, run_id: str) -> ConsoleRunDetail:
        row = self._run_row(run_id)
        summary = self._run_summary(row)
        checkpoint = self._checkpoint(run_id)
        return ConsoleRunDetail(
            **summary.model_dump(),
            checkpoint=checkpoint,
            events=self.get_events(run_id, tail=100),
            artifacts=self.list_artifacts(run_id),
            evidence=self._evidence_summary(run_id),
            release=self._release_summary(run_id),
        )

    def get_events(
        self,
        run_id: str,
        *,
        stage: str | None = None,
        tail: int | None = None,
    ) -> list[ConsoleEvent]:
        try:
            events = self.reports.log_events(run_id, stage_filter=stage, tail=tail)
        except RunReportError as error:
            raise _read_error_from_report(error) from error
        return [ConsoleEvent(**event) for event in events]

    def list_artifacts(self, run_id: str) -> list[ConsoleArtifactSummary]:
        run_dir = self._run_dir(run_id)
        artifacts: list[ConsoleArtifactSummary] = []
        for path in sorted(run_dir.rglob("*.yaml")):
            if "history" in path.relative_to(run_dir).parts:
                continue
            try:
                envelope = ArtifactRepository(run_dir).read(path)
            except (OSError, ValueError):
                continue
            artifacts.append(_artifact_summary(path.relative_to(run_dir).as_posix(), envelope))
        return artifacts

    def get_artifact(self, run_id: str, path: str) -> ConsoleArtifactDetail:
        run_dir = self._run_dir(run_id)
        target = self._safe_file(run_dir, path)
        try:
            envelope = ArtifactRepository(run_dir).read(target)
        except (OSError, ValueError) as error:
            raise ConsoleReadError(
                str(error),
                next_command=f"coductor artifacts {run_id}",
            ) from error
        raw_text, truncated = read_text_preview(target)
        parsed = load_yaml(raw_text)
        summary = _artifact_summary(target.relative_to(run_dir).as_posix(), envelope)
        return ConsoleArtifactDetail(
            **summary.model_dump(),
            raw_text=raw_text,
            parsed_yaml=parsed,
            truncated=truncated,
            inputs=[item.model_dump(mode="json") for item in envelope.inputs],
        )

    def get_report(self, run_id: str) -> str:
        run_dir = self._run_dir(run_id)
        report = run_dir / "delivery-report.md"
        if not report.exists():
            raise ConsoleReadError(
                f"delivery report not found for {run_id}",
                next_command=f"coductor report {run_id}",
            )
        return report.read_text(encoding="utf-8")

    def get_log(self, run_id: str, path: str) -> ConsoleTextFile:
        run_dir = self._run_dir(run_id)
        target = self._safe_file(run_dir, path)
        raw_text, truncated = read_text_preview(target)
        return ConsoleTextFile(
            path=target.relative_to(run_dir).as_posix(),
            raw_text=raw_text,
            truncated=truncated,
        )

    def _run_summary(self, row: dict[str, str]) -> ConsoleRunSummary:
        checkpoint = self._checkpoint(row["run_id"])
        return ConsoleRunSummary(
            run_id=row["run_id"],
            status=row["status"],
            run_dir=row["run_dir"],
            updated_at=row["updated_at"],
            current_stage=checkpoint.current_stage if checkpoint else None,
            last_error=checkpoint.last_error if checkpoint else None,
        )

    def _checkpoint(self, run_id: str) -> ConsoleCheckpointSummary | None:
        data = self.db.get_checkpoint(run_id)
        if data is None:
            return None
        state = WorkflowState.model_validate(data)
        return ConsoleCheckpointSummary(
            current_stage=state.current_stage,
            completed_task_ids=state.completed_task_ids,
            last_error=state.last_error,
            stale_artifacts=state.stale_artifacts,
        )

    def _run_row(self, run_id: str) -> dict[str, str]:
        row = self.db.get_run(run_id)
        if row is None:
            raise ConsoleReadError(
                f"run not found: {run_id}",
                next_command="coductor status",
            )
        return row

    def _run_dir(self, run_id: str) -> Path:
        return Path(self._run_row(run_id)["run_dir"])

    def _safe_file(self, run_dir: Path, path: str) -> Path:
        try:
            target = resolve_run_file(run_dir, path)
        except ConsolePathError as error:
            raise ConsoleReadError(str(error), next_command="coductor artifacts") from error
        if not target.exists():
            raise ConsoleReadError(f"file not found: {path}", next_command="coductor artifacts")
        return target

    def _evidence_summary(self, run_id: str) -> ConsoleEvidenceSummary | None:
        run_dir = self._run_dir(run_id)
        path = run_dir / "07_evidence.yaml"
        if not path.exists():
            return None
        try:
            envelope = ArtifactRepository(run_dir).read(path)
        except (OSError, ValueError):
            return None
        data = envelope.data
        return ConsoleEvidenceSummary(
            final_status=data["final_status"],
            gate_summary=data.get("gate_summary", {}),
            review_summary=data.get("review_summary", {}),
            validation=data.get("validation", {}),
            completed_tasks=data.get("completed_tasks", []),
            evidence_files=data.get("evidence_files", []),
            manual_checks=data.get("manual_checks", []),
            known_risks=data.get("known_risks", []),
        )

    def _release_summary(self, run_id: str) -> ConsoleReleaseSummary | None:
        run_dir = self._run_dir(run_id)
        path = run_dir / "08_release_manifest.yaml"
        if not path.exists():
            return None
        try:
            envelope = ArtifactRepository(run_dir).read(path)
        except (OSError, ValueError):
            return None
        data = envelope.data
        safety = data.get("safety", {})
        return ConsoleReleaseSummary(
            status=data["status"],
            ready=bool(safety.get("ready", False)),
            reasons=safety.get("reasons", []),
            remote_actions_allowed=bool(safety.get("remote_actions_allowed", False)),
            local_commands=data.get("local_commands", []),
            manual_commands=data.get("manual_commands", []),
        )


def _artifact_summary(path: str, envelope: Any) -> ConsoleArtifactSummary:
    return ConsoleArtifactSummary(
        path=path,
        artifact_type=str(envelope.artifact_type),
        status=str(envelope.status),
        revision=envelope.revision,
        sha256=envelope.metadata.content_sha256,
        producer=envelope.producer.name,
    )


def _read_error_from_report(error: RunReportError) -> ConsoleReadError:
    return ConsoleReadError(
        error.message,
        recoverable=error.recoverable,
        next_command=error.next_command,
    )
