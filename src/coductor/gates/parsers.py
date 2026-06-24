"""Gate output parsing and fingerprinting."""

from __future__ import annotations

import hashlib


def failure_fingerprint(command: str, exit_code: int | None, stdout: str, stderr: str) -> str:
    payload = "\n".join([command, str(exit_code), stdout[-2000:], stderr[-2000:]])
    return "sha256:" + hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
