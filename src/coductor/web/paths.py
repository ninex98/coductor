"""Safe file access helpers for the local web console."""

from __future__ import annotations

from pathlib import Path

ALLOWED_PREVIEW_SUFFIXES = {".yaml", ".yml", ".log", ".md", ".diff", ".patch", ".txt"}
MAX_PREVIEW_BYTES = 512_000


class ConsolePathError(ValueError):
    """Raised when a requested console file path is unsafe."""


def resolve_run_file(run_dir: Path, requested_path: str) -> Path:
    requested = Path(requested_path)
    if requested.is_absolute():
        raise ConsolePathError("absolute paths are not allowed")
    if any(part == ".." for part in requested.parts):
        raise ConsolePathError("parent directory traversal is not allowed")
    if requested.suffix not in ALLOWED_PREVIEW_SUFFIXES:
        raise ConsolePathError(f"unsupported file suffix: {requested.suffix}")
    root = run_dir.resolve()
    candidate = (root / requested).resolve()
    if root != candidate and root not in candidate.parents:
        raise ConsolePathError("path escapes run directory")
    return candidate


def read_text_preview(path: Path) -> tuple[str, bool]:
    data = path.read_bytes()
    truncated = len(data) > MAX_PREVIEW_BYTES
    preview = data[:MAX_PREVIEW_BYTES].decode("utf-8", "replace")
    return preview, truncated
