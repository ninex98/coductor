from __future__ import annotations

from coductor.prompts.renderer import render_worker_prompt


def test_worker_prompt_keeps_yaml_contract_owned_by_coductor() -> None:
    prompt = render_worker_prompt("builder", ["02_spec.yaml"], "创建网页小游戏")

    assert "Use the following YAML artifacts as authoritative input" in prompt
    assert "Coductor will wrap this summary in its fixed YAML artifact contract" in prompt
    assert "Return a structured worker_result contract" not in prompt
