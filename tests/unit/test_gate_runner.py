from __future__ import annotations

import sys
from pathlib import Path

from coductor.gates.models import QualityGate
from coductor.gates.runner import GateRunner


def test_gate_runner_records_failure_fingerprint(tmp_path: Path) -> None:
    gate = QualityGate(
        id="unit_tests",
        stage="final",
        command=f"{sys.executable} -c 'import sys; print(\"boom\"); sys.exit(7)'",
        required=True,
        timeout_seconds=30,
    )

    report = GateRunner(tmp_path).run([gate])

    assert report.required_gates_passed is False
    assert report.next_action == "repair"
    assert report.gates[0].status == "failed"
    assert report.gates[0].exit_code == 7
    assert report.gates[0].failure_fingerprint.startswith("sha256:")
    assert (tmp_path / report.gates[0].stdout_path).exists()


def test_gate_runner_redacts_sensitive_output_logs(tmp_path: Path) -> None:
    gate = QualityGate(
        id="secrets",
        stage="final",
        command=(
            f"{sys.executable} -c 'import sys; "
            'print("OPENAI_API_KEY=sk-test-secret"); '
            'print("Authorization: Bearer bearer-secret", file=sys.stderr); '
            "sys.exit(1)'"
        ),
        required=True,
        timeout_seconds=30,
    )

    report = GateRunner(tmp_path).run([gate])

    stdout = (tmp_path / report.gates[0].stdout_path).read_text(encoding="utf-8")
    stderr = (tmp_path / report.gates[0].stderr_path).read_text(encoding="utf-8")
    assert "sk-test-secret" not in stdout
    assert "bearer-secret" not in stderr
    assert "OPENAI_API_KEY=[REDACTED]" in stdout
    assert "Authorization: Bearer [REDACTED]" in stderr


def test_gate_runner_marks_all_required_passed(tmp_path: Path) -> None:
    gate = QualityGate(
        id="unit_tests",
        stage="final",
        command=f"{sys.executable} -c 'print(\"ok\")'",
        required=True,
        timeout_seconds=30,
    )

    report = GateRunner(tmp_path).run([gate])

    assert report.required_gates_passed is True
    assert report.next_action == "review"
    assert report.gates[0].status == "passed"


def test_gate_runner_treats_missing_executable_as_failed_gate(tmp_path: Path) -> None:
    gate = QualityGate(
        id="missing_tool",
        stage="final",
        command="definitely-not-a-real-coductor-command --version",
        required=True,
        timeout_seconds=30,
    )

    report = GateRunner(tmp_path).run([gate])

    assert report.required_gates_passed is False
    assert report.next_action == "repair"
    assert report.gates[0].status == "failed"
    assert report.gates[0].exit_code == 127
    assert report.gates[0].failure_fingerprint.startswith("sha256:")
