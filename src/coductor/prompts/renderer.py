"""Render worker prompts from YAML artifact context."""

from __future__ import annotations


def render_worker_prompt(role: str, context_artifacts: list[str], objective: str) -> str:
    artifacts = "\n".join(f"- {path}" for path in context_artifacts)
    return (
        f"Role: {role}\n"
        f"Objective: {objective}\n"
        "Use the following YAML artifacts as authoritative input:\n"
        f"{artifacts}\n"
        "Return a structured worker_result contract. Do not claim deterministic gates passed."
    )
