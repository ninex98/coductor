from __future__ import annotations

from coductor.domain.enums import ExecutionMode, ExecutionStrategy
from coductor.planning.planner import choose_strategy


def test_auto_prefers_solo_for_tightly_coupled_goal() -> None:
    decision = choose_strategy("修复同一个函数并补充测试", requested_mode=ExecutionMode.AUTO)

    assert decision.strategy == ExecutionStrategy.SOLO


def test_auto_selects_pipeline_for_contract_then_consumer_goal() -> None:
    decision = choose_strategy(
        "先定义 JSON Schema，再让 CLI 输出符合该 Schema",
        requested_mode=ExecutionMode.AUTO,
    )

    assert decision.strategy == ExecutionStrategy.PIPELINE
    assert decision.reasoning


def test_explicit_mode_wins_over_auto_detection() -> None:
    decision = choose_strategy(
        "先定义 JSON Schema，再让 CLI 输出符合该 Schema",
        requested_mode=ExecutionMode.SOLO,
    )

    assert decision.strategy == ExecutionStrategy.SOLO
