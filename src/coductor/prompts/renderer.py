"""Render worker prompts from YAML artifact context."""

from __future__ import annotations

from dataclasses import dataclass

PROMPT_VERSION = "coductor.v2"


@dataclass(frozen=True)
class PromptSection:
    title: str
    items: list[str]


def render_worker_prompt(
    role: str,
    context_artifacts: list[str],
    objective: str,
    *,
    sections: list[PromptSection] | None = None,
    extra_instructions: list[str] | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    artifacts = "\n".join(f"- {path}" for path in context_artifacts)
    lines = [
        f"Prompt-Version: {prompt_version}",
        f"Role: {role}",
        f"Objective: {objective}",
        "Use the following YAML artifacts as authoritative input:",
        artifacts,
    ]
    for section in sections or []:
        if not section.items:
            continue
        lines.append("")
        lines.append(f"{section.title}:")
        lines.extend(f"- {item}" for item in section.items)
    instructions = [*_default_role_instructions(role), *(extra_instructions or [])]
    if instructions:
        lines.append("")
        lines.append("Instructions:")
        lines.extend(f"- {instruction}" for instruction in instructions)
    lines.append("")
    lines.append(
        "Make the required workspace changes directly. Return a concise plain-text summary with "
        "files changed, commands run, and unresolved issues. Coductor will wrap this summary in "
        "its fixed YAML artifact contract; do not claim deterministic gates passed."
    )
    return "\n".join(lines)


def _default_role_instructions(role: str) -> list[str]:
    if role == "reviewer":
        return [
            "Review the final diff, gate report, and goal satisfaction report independently.",
            "If issues exist, emit lines starting with VERDICT:, BLOCKING:, and FINDING:.",
            (
                "Use FINDING fields: severity, category, file, line, description, "
                "recommendation."
            ),
        ]
    if role == "repairer":
        return [
            (
                "Use the failure evidence to make the smallest change that can satisfy "
                "the missing criteria."
            ),
            "Do not broaden scope beyond allowed paths or unrelated refactors.",
        ]
    return [
        "Implement only the task objective and required acceptance criteria.",
        "Respect allowed paths, forbidden paths, expected outputs, and configured quality gates.",
    ]
