"""Config loading, safe YAML, and init scaffolding."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from coductor.artifacts.serializer import dump_yaml, load_yaml
from coductor.config.models import CoductorConfig, QualityGateConfig


def load_config(root: Path) -> CoductorConfig:
    path = root / "coductor.yaml"
    if not path.exists():
        return CoductorConfig.default()
    return CoductorConfig.model_validate(load_yaml(path.read_text(encoding="utf-8")))


def write_config(root: Path, config: CoductorConfig) -> Path:
    path = root / "coductor.yaml"
    path.write_text(dump_yaml(config.model_dump(mode="json")), encoding="utf-8")
    return path


def discover_config(root: Path) -> CoductorConfig:
    config = CoductorConfig.default()
    config.project.name = root.name
    config.quality_gates = _discover_quality_gates(root)
    return config


def _discover_quality_gates(root: Path) -> list[QualityGateConfig]:
    gates: list[QualityGateConfig] = []
    pyproject = root / "pyproject.toml"
    package_json = root / "package.json"
    composer_json = root / "composer.json"
    if pyproject.exists():
        gates.append(
            QualityGateConfig(
                id="unit_tests",
                command=f"{sys.executable} -m pytest -q",
                timeout_seconds=300,
            )
        )
    if package_json.exists():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            package = {}
        scripts: dict[str, Any] = package.get("scripts", {}) if isinstance(package, dict) else {}
        if "test" in scripts:
            gates.append(QualityGateConfig(id="npm_test", command="npm test", timeout_seconds=300))
        if "lint" in scripts:
            gates.append(
                QualityGateConfig(id="npm_lint", command="npm run lint", timeout_seconds=180)
            )
        if "build" in scripts:
            gates.append(
                QualityGateConfig(id="npm_build", command="npm run build", timeout_seconds=300)
            )
    if composer_json.exists():
        gates.append(
            QualityGateConfig(id="composer_test", command="composer test", timeout_seconds=300)
        )
    return gates
