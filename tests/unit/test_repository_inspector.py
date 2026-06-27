from __future__ import annotations

import json
import sys

from coductor.config.models import CoductorConfig
from coductor.repository.inspector import RepositoryInspector


def test_repository_inspector_discovers_node_typecheck_with_package_manager(tmp_path) -> None:
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
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("export const ok = true;\n", encoding="utf-8")

    snapshot = RepositoryInspector(tmp_path, CoductorConfig.default()).inspect()

    assert "JavaScript/TypeScript" in snapshot.languages
    assert "Node.js" in snapshot.frameworks
    assert snapshot.discovered_commands.test == ["pnpm test"]
    assert snapshot.discovered_commands.lint == ["pnpm run lint"]
    assert snapshot.discovered_commands.typecheck == ["pnpm run typecheck"]
    assert snapshot.discovered_commands.build == ["pnpm run build"]


def test_repository_inspector_discovers_configured_python_tools(tmp_path) -> None:
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
    (tmp_path / "example.py").write_text("VALUE: int = 1\n", encoding="utf-8")

    snapshot = RepositoryInspector(tmp_path, CoductorConfig.default()).inspect()

    assert snapshot.discovered_commands.test == [f"{sys.executable} -m pytest -q"]
    assert snapshot.discovered_commands.lint == ["ruff check ."]
    assert snapshot.discovered_commands.typecheck == ["mypy src"]
