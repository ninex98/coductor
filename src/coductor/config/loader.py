"""Config loading, safe YAML, and init scaffolding."""

from __future__ import annotations

import sys
from pathlib import Path

from coductor.artifacts.serializer import dump_yaml, load_yaml
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.repository.node import node_package_manager, node_script_command, node_scripts
from coductor.repository.python import pyproject_tools


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
        tools = pyproject_tools(pyproject)
        if "pytest" in tools:
            gates.append(
                QualityGateConfig(
                    id="python_tests",
                    command=f"{sys.executable} -m pytest -q",
                    timeout_seconds=300,
                )
            )
        if "ruff" in tools:
            gates.append(
                QualityGateConfig(
                    id="python_lint",
                    command="ruff check .",
                    timeout_seconds=120,
                )
            )
        if "mypy" in tools:
            gates.append(
                QualityGateConfig(
                    id="python_typecheck",
                    command="mypy src",
                    timeout_seconds=180,
                )
            )
    if package_json.exists():
        scripts = node_scripts(root)
        package_manager = node_package_manager(root)
        if "test" in scripts:
            gates.append(
                QualityGateConfig(
                    id="node_test",
                    command=node_script_command(package_manager, "test"),
                    timeout_seconds=300,
                )
            )
        if "lint" in scripts:
            gates.append(
                QualityGateConfig(
                    id="node_lint",
                    command=node_script_command(package_manager, "lint"),
                    timeout_seconds=180,
                )
            )
        if "typecheck" in scripts:
            gates.append(
                QualityGateConfig(
                    id="node_typecheck",
                    command=node_script_command(package_manager, "typecheck"),
                    timeout_seconds=180,
                )
            )
        if "build" in scripts:
            gates.append(
                QualityGateConfig(
                    id="node_build",
                    command=node_script_command(package_manager, "build"),
                    timeout_seconds=300,
                )
            )
    if composer_json.exists():
        gates.append(
            QualityGateConfig(id="composer_test", command="composer test", timeout_seconds=300)
        )
    return gates
