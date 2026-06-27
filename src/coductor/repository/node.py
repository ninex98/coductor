"""Node.js package metadata helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def node_package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    return "npm"


def node_scripts(root: Path) -> dict[str, str]:
    package_json = root / "package.json"
    try:
        package = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts: Any = package.get("scripts", {}) if isinstance(package, dict) else {}
    if not isinstance(scripts, dict):
        return {}
    return {
        str(name): str(command)
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str)
    }


def node_script_command(package_manager: str, script: str) -> str:
    if script == "test":
        return f"{package_manager} test"
    return f"{package_manager} run {script}"
