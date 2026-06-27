"""Python project metadata helpers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def pyproject_tools(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    tool: Any = data.get("tool", {}) if isinstance(data, dict) else {}
    if not isinstance(tool, dict):
        return set()
    names = set(tool)
    if isinstance(tool.get("pytest"), dict):
        names.add("pytest")
    return {str(name) for name in names}
