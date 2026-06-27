from __future__ import annotations

from pathlib import Path

import pytest

from coductor.web.paths import ConsolePathError, read_text_preview, resolve_run_file


def test_resolve_run_file_allows_supported_files_inside_run_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    artifact = run_dir / "00_goal.yaml"
    artifact.write_text("artifact_type: goal\n", encoding="utf-8")
    log_dir = run_dir / "logs"
    log_dir.mkdir()
    log = log_dir / "unit_tests.stdout.log"
    log.write_text("passed\n", encoding="utf-8")

    assert resolve_run_file(run_dir, "00_goal.yaml") == artifact.resolve()
    assert resolve_run_file(run_dir, "logs/unit_tests.stdout.log") == log.resolve()


@pytest.mark.parametrize(
    "requested_path",
    [
        "../coductor.yaml",
        "/tmp/coductor.yaml",
        "coductor.sqlite3",
    ],
)
def test_resolve_run_file_rejects_unsafe_or_unsupported_paths(
    tmp_path: Path,
    requested_path: str,
) -> None:
    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()

    with pytest.raises(ConsolePathError):
        resolve_run_file(run_dir, requested_path)


def test_resolve_run_file_rejects_symlink_escape(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("secret: true\n", encoding="utf-8")
    (run_dir / "escape.yaml").symlink_to(outside)

    with pytest.raises(ConsolePathError):
        resolve_run_file(run_dir, "escape.yaml")


def test_read_text_preview_truncates_large_files(tmp_path: Path) -> None:
    path = tmp_path / "large.log"
    path.write_text("x" * 600_000, encoding="utf-8")

    preview, truncated = read_text_preview(path)

    assert len(preview) == 512_000
    assert truncated is True


def test_read_text_preview_redacts_sensitive_values(tmp_path: Path) -> None:
    path = tmp_path / "gate.log"
    path.write_text(
        "Authorization: Bearer bearer-secret\npassword=plain-secret\n",
        encoding="utf-8",
    )

    preview, truncated = read_text_preview(path)

    assert truncated is False
    assert "bearer-secret" not in preview
    assert "plain-secret" not in preview
    assert "Authorization: Bearer [REDACTED]" in preview
    assert "password=[REDACTED]" in preview
