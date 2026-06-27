"""Deterministic quality gate runner."""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Literal

from coductor.artifacts.models import GateReportData, GateResultData
from coductor.gates.models import QualityGate
from coductor.gates.parsers import failure_fingerprint
from coductor.repository.git import current_commit
from coductor.security import redact_sensitive_text

GateStatus = Literal["passed", "failed", "skipped", "timeout"]


class GateRunner:
    def __init__(self, root: Path, *, run_dir: Path | None = None) -> None:
        self.root = root
        self.run_dir = run_dir or root
        (self.run_dir / "logs").mkdir(parents=True, exist_ok=True)

    def run(self, gates: list[QualityGate]) -> GateReportData:
        results = [self._run_gate(gate) for gate in gates]
        required = [result for result in results if result.required]
        required_passed = all(result.status == "passed" for result in required)
        return GateReportData(
            base_commit=current_commit(self.root),
            head_commit=current_commit(self.root),
            gates=results,
            acceptance_coverage=[],
            required_gates_passed=required_passed,
            next_action="review" if required_passed else "repair",
        )

    def _run_gate(self, gate: QualityGate) -> GateResultData:
        start = time.monotonic()
        stdout_path = f"logs/{gate.id}.stdout.log"
        stderr_path = f"logs/{gate.id}.stderr.log"
        try:
            completed = subprocess.run(
                shlex.split(gate.command),
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=gate.timeout_seconds,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code: int | None = completed.returncode
            status: GateStatus = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            stdout = (
                exc.stdout.decode("utf-8", "replace")
                if isinstance(exc.stdout, bytes)
                else exc.stdout or ""
            )
            stderr = (
                exc.stderr.decode("utf-8", "replace")
                if isinstance(exc.stderr, bytes)
                else exc.stderr or ""
            )
            exit_code = None
            status = "timeout"
        except FileNotFoundError as exc:
            stdout = ""
            stderr = f"executable not found: {exc.filename}"
            exit_code = 127
            status = "failed"
        stdout = redact_sensitive_text(stdout)
        stderr = redact_sensitive_text(stderr)
        duration_ms = int((time.monotonic() - start) * 1000)
        (self.run_dir / stdout_path).write_text(stdout, encoding="utf-8")
        (self.run_dir / stderr_path).write_text(stderr, encoding="utf-8")
        fingerprint = None
        if status != "passed":
            fingerprint = failure_fingerprint(gate.command, exit_code, stdout, stderr)
        return GateResultData(
            id=gate.id,
            required=gate.required,
            status=status,
            command=gate.command,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            failure_fingerprint=fingerprint,
        )
