"""Command-backed tool verification with YAML request/result artifacts."""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Literal, cast

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    ArtifactEnvelope,
    ArtifactInput,
    Producer,
    ToolRequestData,
    ToolResultData,
    VerificationPlanData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig, ToolCheckConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ProducerKind
from coductor.domain.tool_paths import (
    tool_request_path_for_check,
    tool_result_path_for_check,
    tool_run_id_for_check,
)
from coductor.gates.parsers import failure_fingerprint
from coductor.security import redact_sensitive_text
from coductor.services.browser_validation_runner import BrowserValidationRunner
from coductor.services.image_asset_runner import ImageAssetRunner, image_parameters
from coductor.services.tool_execution import ToolExecutionResult
from coductor.workflow.artifact_writer import (
    WorkflowArtifactWriter,
    implicit_image_check_for_item,
)

ToolStatus = Literal["passed", "failed", "skipped", "timeout"]


class ToolCapabilityRegistry:
    """Minimal registry for command-backed verification tool kinds."""

    def __init__(self, supported_tools: set[str] | None = None) -> None:
        self.supported_tools = supported_tools or {
            "command",
            "api",
            "browser",
            "screenshot",
            "image",
            "image_generation",
        }

    def is_supported(self, tool: str) -> bool:
        return tool in self.supported_tools


class ToolVerificationService:
    def __init__(
        self,
        root: Path,
        config: CoductorConfig,
        artifacts: WorkflowArtifactWriter,
        *,
        registry: ToolCapabilityRegistry | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.artifacts = artifacts
        self.registry = registry or ToolCapabilityRegistry()

    def run_checks(
        self,
        repo: ArtifactRepository,
        run_id: str,
    ) -> list[ArtifactEnvelope[ToolResultData]]:
        return [
            self.run_check(repo, run_id, check)
            for check in self._checks_for_run(repo)
        ]

    def run_check(
        self,
        repo: ArtifactRepository,
        run_id: str,
        check: ToolCheckConfig,
    ) -> ArtifactEnvelope[ToolResultData]:
        tool_run_id = tool_run_id_for_check(check.id)
        run_path = repo.root / "tool_runs" / tool_run_id
        run_path.mkdir(parents=True, exist_ok=True)
        request_path = tool_request_path_for_check(check.id)
        result_path = tool_result_path_for_check(check.id)
        stdout_path = f"tool_runs/{tool_run_id}/stdout.log"
        stderr_path = f"tool_runs/{tool_run_id}/stderr.log"
        request = self._write_request(
            repo,
            run_id,
            check,
            tool_run_id=tool_run_id,
            request_path=request_path,
            result_path=result_path,
        )
        execution = self._execute(check, run_path=run_path, tool_run_id=tool_run_id)
        command = _display_command(check)
        stdout = redact_sensitive_text(execution.stdout)
        stderr = redact_sensitive_text(execution.stderr)
        (repo.root / stdout_path).write_text(stdout, encoding="utf-8")
        (repo.root / stderr_path).write_text(stderr, encoding="utf-8")
        artifacts = sorted(
            {
                path
                for path in [*check.evidence_paths, *execution.artifacts]
                if (repo.root / path).exists()
            }
        )
        artifact_hashes = {
            path: file_sha256(repo.root / path)
            for path in artifacts
            if (repo.root / path).is_file()
        }
        evidence_paths = [result_path, *artifacts]
        fingerprint = None
        if execution.status != "passed":
            fingerprint = failure_fingerprint(command, execution.exit_code, stdout, stderr)
        data = ToolResultData(
            tool_run_id=tool_run_id,
            check_id=check.id,
            tool=check.tool,
            required=check.required,
            status=execution.status,
            command=command,
            exit_code=execution.exit_code,
            duration_ms=execution.duration_ms,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            artifacts=artifacts,
            artifact_hashes=artifact_hashes,
            evidence_paths=evidence_paths,
            observations=execution.observations,
            failure_fingerprint=fingerprint,
        )
        envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.TOOL_RESULT,
            artifact_id_prefix="art_tool_result",
            status=(
                ArtifactStatus.PASSED
                if execution.status == "passed"
                else ArtifactStatus.FAILED
            ),
            producer=Producer(kind=ProducerKind.TOOL, name="tool-verification-service"),
            inputs=[ArtifactInput.model_validate(repo.input_for(request_path, request))],
            data=data,
        )
        return _write_revision(repo, result_path, envelope)

    def _write_request(
        self,
        repo: ArtifactRepository,
        run_id: str,
        check: ToolCheckConfig,
        *,
        tool_run_id: str,
        request_path: str,
        result_path: str,
    ) -> ArtifactEnvelope[ToolRequestData]:
        data = ToolRequestData(
            tool_run_id=tool_run_id,
            check_id=check.id,
            tool=check.tool,
            command=_display_command(check),
            required=check.required,
            timeout_seconds=check.timeout_seconds,
            description=check.description,
            evidence_paths=[result_path, *check.evidence_paths],
            parameters=_tool_parameters(check),
        )
        envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.TOOL_REQUEST,
            artifact_id_prefix="art_tool_request",
            status=ArtifactStatus.READY,
            producer=Producer(kind=ProducerKind.SYSTEM, name="tool-verification-service"),
            data=data,
        )
        return _write_revision(repo, request_path, envelope)

    def _execute(
        self,
        check: ToolCheckConfig,
        *,
        run_path: Path,
        tool_run_id: str,
    ) -> ToolExecutionResult:
        start = time.monotonic()
        if not self.registry.is_supported(check.tool):
            return ToolExecutionResult(
                status="skipped",
                exit_code=None,
                duration_ms=0,
                stdout="",
                stderr=f"unsupported tool: {check.tool}",
            )
        if check.tool == "browser" and _is_browser_runner_check(check):
            return BrowserValidationRunner(
                self.root,
                run_dir=run_path,
                tool_run_id=tool_run_id,
            ).run(check)
        if check.tool in {"image", "image_generation"} and not check.command.strip():
            return ImageAssetRunner(self.root, run_dir=run_path).run(check)
        if not check.command.strip():
            return ToolExecutionResult(
                status="failed",
                exit_code=2,
                duration_ms=0,
                stdout="",
                stderr="tool check command is empty",
            )
        try:
            completed = subprocess.run(
                shlex.split(check.command),
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=check.timeout_seconds,
                check=False,
            )
            status: ToolStatus = "passed" if completed.returncode == 0 else "failed"
            exit_code: int | None = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            status = "timeout"
            exit_code = None
            stdout = _timeout_output(exc.stdout)
            stderr = _timeout_output(exc.stderr)
        except FileNotFoundError as exc:
            status = "failed"
            exit_code = 127
            stdout = ""
            stderr = f"executable not found: {exc.filename}"
        duration_ms = int((time.monotonic() - start) * 1000)
        return ToolExecutionResult(
            status=status,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout=stdout,
            stderr=stderr,
        )

    def _checks_for_run(self, repo: ArtifactRepository) -> list[ToolCheckConfig]:
        checks = list(self.config.tool_checks)
        seen = {check.id for check in checks}
        verification_path = repo.root / "03_verification_plan.yaml"
        if not verification_path.exists():
            return checks
        try:
            plan = ArtifactEnvelope[VerificationPlanData].model_validate(
                repo.read(
                    "03_verification_plan.yaml",
                    ArtifactType.VERIFICATION_PLAN,
                ).model_dump(mode="json")
            )
        except (OSError, ValueError):
            return checks
        for item in plan.data.items:
            implicit = implicit_image_check_for_item(item)
            if implicit is None or implicit.id in seen:
                continue
            checks.append(implicit)
            seen.add(implicit.id)
        return checks


def _is_browser_runner_check(check: ToolCheckConfig) -> bool:
    return (
        bool(check.browser.url)
        or bool(check.browser.static_path)
        or bool(check.browser.start_command)
        or not check.command.strip()
    )


def _display_command(check: ToolCheckConfig) -> str:
    if check.command.strip():
        return redact_sensitive_text(check.command)
    if check.tool == "browser":
        return "generated-browser-smoke"
    if check.tool in {"image", "image_generation"}:
        return "image-asset-request"
    return ""


def _tool_parameters(check: ToolCheckConfig) -> dict[str, Any]:
    if check.tool == "browser":
        return {
            "url": check.browser.url,
            "static_path": check.browser.static_path,
            "start_command": check.browser.start_command,
            "viewport_width": check.browser.viewport_width,
            "viewport_height": check.browser.viewport_height,
            "selectors": check.browser.selectors,
            "text": check.browser.text,
            "fail_on_console_error": check.browser.fail_on_console_error,
            "screenshot": check.browser.screenshot,
        }
    if check.tool in {"image", "image_generation"}:
        return image_parameters(check)
    return {}


def _write_revision[EnvelopeT: ArtifactEnvelope[Any]](
    repo: ArtifactRepository,
    relative_path: str,
    envelope: EnvelopeT,
) -> EnvelopeT:
    if (repo.root / relative_path).exists():
        return cast(EnvelopeT, repo.write_next_revision(relative_path, envelope))
    repo.write(relative_path, envelope)
    return envelope


def _timeout_output(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""
