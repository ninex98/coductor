"""Small redaction helpers for persisted logs and console previews."""

from __future__ import annotations

import re

REDACTION_TEXT = "[REDACTED]"

_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s'\"<>]+)",
        ),
        rf"\1{REDACTION_TEXT}",
    ),
    (
        re.compile(
            (
                r"(?i)\b("
                r"(?:[a-z0-9]+[_-])*"
                r"(?:api[_-]?key|token|password|secret)"
                r"\s*[:=]\s*"
                r")([^\s'\"<>]+)"
            ),
        ),
        rf"\1{REDACTION_TEXT}",
    ),
)


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_sensitive_list(values: list[str]) -> list[str]:
    return [redact_sensitive_text(value) for value in values]
