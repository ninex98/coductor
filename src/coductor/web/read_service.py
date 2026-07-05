"""Read-only data facade for the local web console."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import load_yaml
from coductor.constants import CODUCTOR_DIR, VERSION
from coductor.domain.enums import ArtifactType
from coductor.services.report_service import ReportService, RunReportError
from coductor.storage.database import Database
from coductor.web.paths import ConsolePathError, read_text_preview, resolve_run_file
from coductor.web.schemas import (
    ConsoleArtifactDetail,
    ConsoleArtifactSummary,
    ConsoleCheckpointSummary,
    ConsoleEvent,
    ConsoleEvidenceSummary,
    ConsoleGoalCriterionSummary,
    ConsoleGoalLoopSummary,
    ConsoleHealth,
    ConsoleReleaseSummary,
    ConsoleRepairSummary,
    ConsoleRunDetail,
    ConsoleRunSummary,
    ConsoleTextFile,
    ConsoleToolEvidenceSummary,
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
            goal_loop=self._goal_loop_summary(run_id, checkpoint),
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
        run_dir_error = self._run_dir_boundary_error(row)
        return ConsoleRunSummary(
            run_id=row["run_id"],
            status=row["status"],
            run_dir=row["run_dir"],
            updated_at=row["updated_at"],
            current_stage=checkpoint.current_stage if checkpoint else None,
            last_error=checkpoint.last_error if checkpoint else None,
            run_dir_valid=run_dir_error is None,
            run_dir_error=run_dir_error,
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
        row = self._run_row(run_id)
        error = self._run_dir_boundary_error(row)
        if error is not None:
            raise ConsoleReadError(error, next_command=f"coductor status {run_id}")
        return Path(row["run_dir"]).resolve()

    def _run_dir_boundary_error(self, row: dict[str, str]) -> str | None:
        run_id = row["run_id"]
        run_dir = Path(row["run_dir"])
        expected_root = (self.root / CODUCTOR_DIR / "runs").resolve()
        resolved = run_dir.resolve()
        expected = (expected_root / run_id).resolve()
        if resolved != expected:
            return f"run_dir is outside project runs directory: {run_dir}"
        return None

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
            goal_satisfaction=data.get("goal_satisfaction", {}),
            validation=data.get("validation", {}),
            completed_tasks=data.get("completed_tasks", []),
            evidence_files=data.get("evidence_files", []),
            manual_checks=data.get("manual_checks", []),
            known_risks=data.get("known_risks", []),
        )

    def _goal_loop_summary(
        self,
        run_id: str,
        checkpoint: ConsoleCheckpointSummary | None,
    ) -> ConsoleGoalLoopSummary | None:
        run_dir = self._run_dir(run_id)
        repo = ArtifactRepository(run_dir)
        verification = _artifact_data(
            repo,
            "03_verification_plan.yaml",
            ArtifactType.VERIFICATION_PLAN,
        )
        satisfaction = _artifact_data(
            repo,
            "07_goal_satisfaction.yaml",
            ArtifactType.GOAL_SATISFACTION_REPORT,
        )
        tools = _tool_summaries(repo)
        repairs = _repair_summaries(repo)
        raw_checkpoint = self.db.get_checkpoint(run_id)
        has_checkpoint_loop = bool(
            checkpoint
            and (
                checkpoint.stale_artifacts
                or _checkpoint_int(raw_checkpoint, "goal_iteration")
                or _checkpoint_int(raw_checkpoint, "satisfaction_repair_attempts")
            )
        )
        if not any([verification, satisfaction, tools, repairs, has_checkpoint_loop]):
            return None

        criteria = _criterion_summaries(verification, satisfaction)
        counts = _criterion_counts(criteria)
        return ConsoleGoalLoopSummary(
            verdict=str(satisfaction.get("verdict", "pending") if satisfaction else "pending"),
            satisfied=counts["satisfied"],
            not_satisfied=counts["not_satisfied"],
            uncertain=counts["uncertain"],
            unknown=counts["unknown"],
            planned_criteria=len(criteria),
            all_required_criteria_planned=(
                verification.get("all_required_criteria_planned") if verification else None
            ),
            warnings=list(verification.get("warnings", []) if verification else []),
            missing_evidence=list(satisfaction.get("missing_evidence", []) if satisfaction else []),
            repair_recommendation=(
                satisfaction.get("repair_recommendation") if satisfaction else None
            ),
            requires_repair=bool(satisfaction.get("requires_repair", False))
            if satisfaction
            else False,
            requires_human=bool(satisfaction.get("requires_human", False))
            if satisfaction
            else False,
            goal_iteration=_checkpoint_int(raw_checkpoint, "goal_iteration"),
            satisfaction_repair_attempts=_checkpoint_int(
                raw_checkpoint,
                "satisfaction_repair_attempts",
            ),
            last_satisfaction_error=_checkpoint_str(raw_checkpoint, "last_satisfaction_error"),
            stale_artifacts=checkpoint.stale_artifacts if checkpoint else [],
            criteria=criteria,
            tools=tools,
            repairs=repairs,
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


def _artifact_data(
    repo: ArtifactRepository,
    path: str,
    artifact_type: ArtifactType,
) -> dict[str, Any] | None:
    target = repo.root / path
    if not target.exists():
        return None
    try:
        envelope = repo.read(path, artifact_type)
    except (OSError, ValueError):
        return None
    data = envelope.data
    if isinstance(data, dict):
        return data
    if hasattr(data, "model_dump"):
        dumped = data.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else None
    return None


def _criterion_summaries(
    verification: dict[str, Any] | None,
    satisfaction: dict[str, Any] | None,
) -> list[ConsoleGoalCriterionSummary]:
    plan_items = _dict_list(verification.get("items", []) if verification else [])
    satisfaction_results = _dict_list(
        satisfaction.get("criterion_results", []) if satisfaction else []
    )
    result_by_criterion = {
        str(result.get("criterion_id", "")): result
        for result in satisfaction_results
        if result.get("criterion_id")
    }
    criteria: list[ConsoleGoalCriterionSummary] = []
    seen: set[str] = set()
    for item in plan_items:
        criterion_id = str(item.get("criterion_id", ""))
        if not criterion_id:
            continue
        seen.add(criterion_id)
        result = result_by_criterion.get(criterion_id, {})
        criteria.append(
            ConsoleGoalCriterionSummary(
                criterion_id=criterion_id,
                description=_optional_str(item.get("description")),
                verification=_optional_str(item.get("verification")),
                tool=_optional_str(item.get("tool")),
                required=bool(item.get("required", True)),
                status=str(result.get("status", "unknown")),
                evidence=_string_list(result.get("evidence", [])),
                missing_evidence=_string_list(result.get("missing_evidence", [])),
                reason=_optional_str(result.get("reason")),
            )
        )
    for result in satisfaction_results:
        criterion_id = str(result.get("criterion_id", ""))
        if not criterion_id or criterion_id in seen:
            continue
        criteria.append(
            ConsoleGoalCriterionSummary(
                criterion_id=criterion_id,
                status=str(result.get("status", "unknown")),
                evidence=_string_list(result.get("evidence", [])),
                missing_evidence=_string_list(result.get("missing_evidence", [])),
                reason=_optional_str(result.get("reason")),
            )
        )
    return criteria


def _criterion_counts(criteria: list[ConsoleGoalCriterionSummary]) -> dict[str, int]:
    counts = {"satisfied": 0, "not_satisfied": 0, "uncertain": 0, "unknown": 0}
    for criterion in criteria:
        if criterion.status in counts:
            counts[criterion.status] += 1
        else:
            counts["unknown"] += 1
    return counts


def _tool_summaries(repo: ArtifactRepository) -> list[ConsoleToolEvidenceSummary]:
    tool_root = repo.root / "tool_runs"
    if not tool_root.exists():
        return []
    summaries: list[ConsoleToolEvidenceSummary] = []
    for path in sorted(tool_root.glob("*/tool_result.yaml")):
        relative_path = path.relative_to(repo.root).as_posix()
        data = _artifact_data(repo, relative_path, ArtifactType.TOOL_RESULT)
        if data is None:
            continue
        summaries.append(
            ConsoleToolEvidenceSummary(
                path=relative_path,
                check_id=str(data.get("check_id", "")),
                tool_run_id=str(data.get("tool_run_id", path.parent.name)),
                tool=str(data.get("tool", "")),
                required=bool(data.get("required", True)),
                status=str(data.get("status", "unknown")),
                command=str(data.get("command", "")),
                duration_ms=int(data.get("duration_ms", 0) or 0),
                stdout_path=str(data.get("stdout_path", "")),
                stderr_path=str(data.get("stderr_path", "")),
                artifacts=_string_list(data.get("artifacts", [])),
                evidence_paths=_string_list(data.get("evidence_paths", [])),
                observations=(
                    data["observations"] if isinstance(data.get("observations"), dict) else {}
                ),
                failure_fingerprint=_optional_str(data.get("failure_fingerprint")),
            )
        )
    return summaries


def _repair_summaries(repo: ArtifactRepository) -> list[ConsoleRepairSummary]:
    repair_root = repo.root / "repairs"
    if not repair_root.exists():
        return []
    summaries: list[ConsoleRepairSummary] = []
    for path in sorted(repair_root.glob("*/repair_request.yaml")):
        relative_path = path.relative_to(repo.root).as_posix()
        data = _artifact_data(repo, relative_path, ArtifactType.REPAIR_REQUEST)
        if data is None:
            continue
        summaries.append(
            ConsoleRepairSummary(
                path=relative_path,
                reason=str(data.get("reason", "")),
                attempt=int(data.get("attempt", 0) or 0),
                max_attempts=int(data.get("max_attempts", 0) or 0),
                missing_criteria=_string_list(data.get("missing_criteria", [])),
                missing_evidence=_string_list(data.get("missing_evidence", [])),
                recommended_action=_optional_str(data.get("recommended_action")),
            )
        )
    return summaries


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _checkpoint_int(data: Mapping[str, Any] | None, field: str) -> int:
    if data is None:
        return 0
    try:
        return int(data.get(field, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _checkpoint_str(data: Mapping[str, Any] | None, field: str) -> str | None:
    if data is None or data.get(field) is None:
        return None
    return str(data[field])


def _read_error_from_report(error: RunReportError) -> ConsoleReadError:
    return ConsoleReadError(
        error.message,
        recoverable=error.recoverable,
        next_command=error.next_command,
    )
