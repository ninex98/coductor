"""Read-only diagnostics for the local web console."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from coductor.backends.capabilities import describe_backend_capability, effective_backend_provider
from coductor.backends.factory import is_codex_sdk_available, resolve_codex_bin
from coductor.config.loader import discover_config, load_config
from coductor.constants import CODUCTOR_DIR, VERSION
from coductor.web.schemas import ConsoleDoctorReport


class ConsoleDoctorService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def report(self) -> ConsoleDoctorReport:
        config_path = self.root / "coductor.yaml"
        config = load_config(self.root) if config_path.exists() else discover_config(self.root)
        sdk_available = is_codex_sdk_available()
        effective_provider = effective_backend_provider(
            config.backend.provider,
            fallback=config.backend.fallback,
            sdk_available=sdk_available,
        )
        capability = describe_backend_capability(
            effective_provider,
            sdk_available=sdk_available,
        )
        checks = {
            "coductor_version": VERSION,
            "python": sys.version.split()[0],
            "git": shutil.which("git") or "missing",
            "codex": shutil.which("codex") or "missing",
            "config": "present" if config_path.exists() else "missing",
            "database": (
                "present"
                if (self.root / CODUCTOR_DIR / "coductor.sqlite3").exists()
                else "not initialized"
            ),
            "backend_provider": config.backend.provider,
            "backend_effective_provider": effective_provider,
            "backend_fallback": config.backend.fallback,
            "backend_available": capability.available,
            "codex_exec_bin": resolve_codex_bin(),
            "codex_sdk_available": sdk_available,
            "backend_capabilities": capability.model_dump(mode="json"),
            "permission_defaults": {
                "network_access": config.permissions.network_access,
                "allow_git_commit": config.permissions.allow_git_commit,
                "allow_git_push": config.permissions.allow_git_push,
                "allow_pull_request": config.permissions.allow_pull_request,
            },
            "quality_gates": [
                gate.model_dump(mode="json") for gate in config.quality_gates
            ],
        }
        return ConsoleDoctorReport(checks=checks)
