"""Solo-first deterministic planner for Phase 1."""

from __future__ import annotations

from coductor.artifacts.models import ExecutionPlanData, PlanTask, SpecificationData
from coductor.domain.enums import ExecutionStrategy, SandboxMode, TaskType
from coductor.planning.validator import PlanValidator


def create_solo_plan(spec: SpecificationData, base_commit: str) -> ExecutionPlanData:
    criteria_ids = [
        criterion.id
        for criterion in spec.acceptance_criteria
        if criterion.priority == "required"
    ]
    task = PlanTask(
        id="T001",
        title="完成目标契约中的功能实现和相关测试",
        task_type=TaskType.INTEGRATED_IMPLEMENTATION,
        role="builder",
        depends_on=[],
        consumes=["02_spec.yaml", "01_repository_snapshot.yaml"],
        produces=["tasks/T001/worker_result.yaml"],
        allowed_paths=["src/**", "tests/**", "docs/**", "examples/**"],
        forbidden_paths=[".env*", "**/secrets/**", "**/production/**"],
        acceptance_criteria=criteria_ids,
        quality_gates=["unit_tests"],
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.SOLO,
        strategy_reasoning=[
            "auto 模式默认倾向 solo；当前目标可由一个连续上下文完成"
        ],
        base_commit=base_commit,
        tasks=[task],
        graph={"edges": []},
    )
    plan.validation = PlanValidator(
        acceptance_criteria=spec.acceptance_criteria,
        produced_artifacts={"02_spec.yaml", "01_repository_snapshot.yaml"},
    ).validate(plan)
    return plan
