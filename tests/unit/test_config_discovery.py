from __future__ import annotations

import json
import sys

from coductor.config.loader import discover_config


def test_discover_config_uses_package_manager_and_typecheck_scripts(tmp_path) -> None:
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": "vitest run",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "build": "vite build",
                }
            }
        ),
        encoding="utf-8",
    )

    config = discover_config(tmp_path)

    gates = {gate.id: gate.command for gate in config.quality_gates}
    assert gates == {
        "node_test": "pnpm test",
        "node_lint": "pnpm run lint",
        "node_typecheck": "pnpm run typecheck",
        "node_build": "pnpm run build",
    }
    assert len(config.tool_checks) == 0


def test_discover_config_adds_browser_smoke_for_ui_scripts(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "dev": "vite --host 127.0.0.1 --port 3000",
                    "build": "vite build",
                }
            }
        ),
        encoding="utf-8",
    )

    config = discover_config(tmp_path)

    assert len(config.tool_checks) == 1
    check = config.tool_checks[0]
    assert check.id == "browser_smoke"
    assert check.tool == "browser"
    assert check.browser.start_command == "npm run dev"
    assert check.browser.url == "http://127.0.0.1:3000"


def test_discover_config_python_project_uses_configured_python_gates(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                "name = 'demo'",
                "[tool.pytest.ini_options]",
                "pythonpath = ['.']",
                "[tool.ruff]",
                "line-length = 100",
                "[tool.mypy]",
                "python_version = '3.12'",
            ]
        ),
        encoding="utf-8",
    )

    config = discover_config(tmp_path)

    gates = {gate.id: gate.command for gate in config.quality_gates}
    assert gates == {
        "python_tests": f"{sys.executable} -m pytest -q",
        "python_lint": "ruff check .",
        "python_typecheck": "mypy src",
    }


def test_discover_config_python_project_omits_unconfigured_python_tools(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                "name = 'demo'",
                "[tool.pytest.ini_options]",
                "pythonpath = ['.']",
            ]
        ),
        encoding="utf-8",
    )

    config = discover_config(tmp_path)

    gates = {gate.id: gate.command for gate in config.quality_gates}
    assert gates == {"python_tests": f"{sys.executable} -m pytest -q"}


def test_discover_config_empty_project_has_no_quality_gates(tmp_path) -> None:
    config = discover_config(tmp_path)

    assert config.quality_gates == []
    assert config.tool_checks == []
