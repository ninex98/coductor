"""Solo-first deterministic planner for Phase 1."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from coductor.artifacts.models import ExecutionPlanData, PlanTask, SpecificationData
from coductor.domain.enums import ExecutionMode, ExecutionStrategy, SandboxMode, TaskType
from coductor.planning.validator import PlanValidator


class StrategyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    strategy: ExecutionStrategy
    reasoning: list[str]


DEPENDENCY_MARKERS = ("先", "再", "schema", "contract", "openapi", "上游", "下游")


def choose_strategy(
    raw_goal: str,
    *,
    requested_mode: ExecutionMode = ExecutionMode.AUTO,
) -> StrategyDecision:
    if requested_mode != ExecutionMode.AUTO:
        return StrategyDecision(
            strategy=ExecutionStrategy(requested_mode.value),
            reasoning=[f"用户显式请求 {requested_mode.value} 模式"],
        )
    normalized = raw_goal.lower()
    markers = [marker for marker in DEPENDENCY_MARKERS if marker in normalized]
    if len(markers) >= 2:
        return StrategyDecision(
            strategy=ExecutionStrategy.PIPELINE,
            reasoning=[
                "目标包含明确的先后依赖信号",
                f"检测到依赖标记: {', '.join(markers)}",
            ],
        )
    return StrategyDecision(
        strategy=ExecutionStrategy.SOLO,
        reasoning=["目标未呈现稳定的多任务依赖，采用 solo 连续上下文"],
    )


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


def create_pipeline_plan(
    spec: SpecificationData,
    base_commit: str,
    reasoning: list[str],
) -> ExecutionPlanData:
    criteria_ids = [
        criterion.id
        for criterion in spec.acceptance_criteria
        if criterion.priority == "required"
    ]
    contract_task = PlanTask(
        id="T001",
        title="定义并稳定上游契约",
        task_type=TaskType.CONTRACT_AUTHORING,
        role="builder",
        depends_on=[],
        consumes=["02_spec.yaml", "01_repository_snapshot.yaml"],
        produces=["tasks/T001/worker_result.yaml", "contracts/generated.schema.json"],
        allowed_paths=["src/**", "tests/**", "docs/**", "examples/**", "contracts/**"],
        forbidden_paths=[".env*", "**/secrets/**", "**/production/**"],
        acceptance_criteria=[],
        quality_gates=["unit_tests"],
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )
    consumer_task = PlanTask(
        id="T002",
        title="基于上游契约完成消费者实现和验证",
        task_type=TaskType.INTEGRATED_IMPLEMENTATION,
        role="builder",
        depends_on=["T001"],
        consumes=[
            "02_spec.yaml",
            "01_repository_snapshot.yaml",
            "tasks/T001/worker_result.yaml",
            "contracts/generated.schema.json",
        ],
        produces=["tasks/T002/worker_result.yaml"],
        allowed_paths=["src/**", "tests/**", "docs/**", "examples/**"],
        forbidden_paths=[".env*", "**/secrets/**", "**/production/**"],
        acceptance_criteria=criteria_ids,
        quality_gates=["unit_tests"],
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.PIPELINE,
        strategy_reasoning=reasoning,
        base_commit=base_commit,
        tasks=[contract_task, consumer_task],
        graph={"edges": [["T001", "T002"]]},
    )
    plan.validation = PlanValidator(
        acceptance_criteria=spec.acceptance_criteria,
        produced_artifacts={
            "02_spec.yaml",
            "01_repository_snapshot.yaml",
            "tasks/T001/worker_result.yaml",
            "contracts/generated.schema.json",
        },
    ).validate(plan)
    return plan
