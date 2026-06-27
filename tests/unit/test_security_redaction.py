from __future__ import annotations

import pytest

from coductor.security import redact_sensitive_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("OPENAI_API_KEY=sk-proj-abc123", "OPENAI_API_KEY=[REDACTED]"),
        ("GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456", "GITHUB_TOKEN=[REDACTED]"),
        ("github: ghs_abcdefghijklmnopqrstuvwxyz123456", "github: [REDACTED]"),
        ("aws_key=AKIAIOSFODNN7EXAMPLE", "aws_key=[REDACTED]"),
        (
            "url=https://api.example.test/cb?token=plain-secret&ok=1",
            "url=https://api.example.test/cb?token=[REDACTED]&ok=1",
        ),
        (
            '{"secret": "json-secret", "name": "demo"}',
            '{"secret": "[REDACTED]", "name": "demo"}',
        ),
        ('password: "yaml-secret"', 'password: "[REDACTED]"'),
    ],
)
def test_redact_sensitive_text_handles_common_secret_shapes(
    raw: str,
    expected: str,
) -> None:
    assert redact_sensitive_text(raw) == expected


def test_redact_sensitive_text_preserves_non_secret_values() -> None:
    raw = "status=ready token_count=42 secretariat=public"

    assert redact_sensitive_text(raw) == raw
