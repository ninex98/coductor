"""Deterministic repository inspection."""

from __future__ import annotations

import sys
from pathlib import Path

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import (
    DiscoveredCommands,
    RepositoryManifest,
    RepositorySnapshotData,
)
from coductor.config.models import CoductorConfig
from coductor.repository.git import current_commit, is_dirty
from coductor.repository.node import node_package_manager, node_script_command, node_scripts
from coductor.repository.python import pyproject_tools


class RepositoryInspector:
    def __init__(self, root: Path, config: CoductorConfig) -> None:
        self.root = root
        self.config = config

    def inspect(self) -> RepositorySnapshotData:
        manifests = self._manifests()
        languages = self._languages()
        in_git_repo = current_commit(self.root) != "NO_GIT_REPOSITORY"
        return RepositorySnapshotData(
            base_commit=current_commit(self.root),
            dirty_worktree=is_dirty(self.root),
            languages=languages,
            frameworks=self._frameworks(manifests),
            manifests=manifests,
            relevant_paths=[],
            discovered_commands=self._commands(manifests),
            existing_documents=self._documents(),
            protected_paths=self.config.permissions.protected_paths,
            risks=[] if in_git_repo else ["当前目录不是 Git 仓库"],
            unknowns=[],
        )

    def _manifests(self) -> list[RepositoryManifest]:
        names = [
            "pyproject.toml",
            "package.json",
            "composer.json",
            "README.md",
            ".github/workflows",
        ]
        manifests: list[RepositoryManifest] = []
        for name in names:
            path = self.root / name
            if path.is_file():
                manifests.append(RepositoryManifest(path=name, sha256=file_sha256(path)))
            elif path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file():
                        manifests.append(
                            RepositoryManifest(
                                path=child.relative_to(self.root).as_posix(),
                                sha256=file_sha256(child),
                            )
                        )
        return manifests

    def _languages(self) -> list[str]:
        suffixes = {path.suffix for path in self.root.rglob("*") if path.is_file()}
        languages: list[str] = []
        if ".py" in suffixes:
            languages.append("Python")
        if {".ts", ".tsx", ".js", ".jsx"} & suffixes:
            languages.append("JavaScript/TypeScript")
        if ".php" in suffixes:
            languages.append("PHP")
        return languages

    def _frameworks(self, manifests: list[RepositoryManifest]) -> list[str]:
        paths = {manifest.path for manifest in manifests}
        frameworks: list[str] = []
        if "pyproject.toml" in paths:
            frameworks.append("Python packaging")
        if "package.json" in paths:
            frameworks.append("Node.js")
        if "composer.json" in paths:
            frameworks.append("Composer")
        return frameworks

    def _commands(self, manifests: list[RepositoryManifest]) -> DiscoveredCommands:
        paths = {manifest.path for manifest in manifests}
        commands = DiscoveredCommands()
        if "pyproject.toml" in paths:
            tools = pyproject_tools(self.root / "pyproject.toml")
            if "pytest" in tools:
                commands.test.append(f"{sys.executable} -m pytest -q")
            if "ruff" in tools:
                commands.lint.append("ruff check .")
            if "mypy" in tools:
                commands.typecheck.append("mypy src")
        if "package.json" in paths:
            package_manager = node_package_manager(self.root)
            scripts = node_scripts(self.root)
            if "test" in scripts:
                commands.test.append(node_script_command(package_manager, "test"))
            if "lint" in scripts:
                commands.lint.append(node_script_command(package_manager, "lint"))
            if "typecheck" in scripts:
                commands.typecheck.append(node_script_command(package_manager, "typecheck"))
            if "build" in scripts:
                commands.build.append(node_script_command(package_manager, "build"))
        return commands

    def _documents(self) -> list[str]:
        docs: list[str] = []
        for name in ["README.md", "AGENTS.md", "docs/architecture.md", "docs/workflow.md"]:
            if (self.root / name).exists():
                docs.append(name)
        return docs
