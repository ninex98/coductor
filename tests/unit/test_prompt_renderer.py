from __future__ import annotations

from coductor.prompts.renderer import PromptSection, render_worker_prompt


def test_worker_prompt_keeps_yaml_contract_owned_by_coductor() -> None:
    prompt = render_worker_prompt("builder", ["02_spec.yaml"], "创建网页小游戏")

    assert "Use the following YAML artifacts as authoritative input" in prompt
    assert "Coductor will wrap this summary in its fixed YAML artifact contract" in prompt
    assert "Return a structured worker_result contract" not in prompt


def test_worker_prompt_includes_structured_sections_and_version() -> None:
    prompt = render_worker_prompt(
        "builder",
        ["02_spec.yaml", "03_verification_plan.yaml"],
        "修复 CLI evidence",
        sections=[
            PromptSection(
                "Acceptance Criteria",
                ["AC001 [required/automated]: evidence bundle must be valid"],
            )
        ],
    )

    assert "Prompt-Version: coductor.v2" in prompt
    assert "Acceptance Criteria:" in prompt
    assert "AC001 [required/automated]" in prompt
    assert "Implement only the task objective" in prompt


def test_reviewer_prompt_includes_structured_output_instructions() -> None:
    prompt = render_worker_prompt(
        "reviewer",
        ["05_gate_report.yaml", "07_goal_satisfaction.yaml"],
        "independently review the verified change",
    )

    assert "VERDICT:" in prompt
    assert "BLOCKING:" in prompt
    assert "FINDING:" in prompt
