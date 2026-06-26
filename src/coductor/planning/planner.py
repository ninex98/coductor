"""Solo-first deterministic planner for Phase 1."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from coductor.artifacts.models import (
    ExecutionPlanData,
    PlanTask,
    RepositorySnapshotData,
    SpecificationData,
)
from coductor.domain.enums import ExecutionMode, ExecutionStrategy, SandboxMode, TaskType
from coductor.planning.spec_builder import derive_allowed_paths, derive_quality_gates
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


def create_solo_plan(
    spec: SpecificationData,
    base_commit: str,
    snapshot: RepositorySnapshotData | None = None,
    *,
    quality_gate_ids: list[str] | None = None,
) -> ExecutionPlanData:
    criteria_ids = [
        criterion.id
        for criterion in spec.acceptance_criteria
        if criterion.priority == "required"
    ]
    allowed_paths = derive_allowed_paths(
        spec.objective,
        snapshot or RepositorySnapshotData(base_commit=base_commit, dirty_worktree=False),
    )
    task = PlanTask(
        id="T001",
        title="完成目标契约中的功能实现和相关测试",
        task_type=TaskType.INTEGRATED_IMPLEMENTATION,
        role="builder",
        depends_on=[],
        consumes=["02_spec.yaml", "01_repository_snapshot.yaml"],
        produces=["tasks/T001/worker_result.yaml"],
        allowed_paths=allowed_paths,
        forbidden_paths=[".env*", "**/secrets/**", "**/production/**"],
        acceptance_criteria=criteria_ids,
        quality_gates=derive_quality_gates(_gate_ids_or_default(quality_gate_ids), criteria_ids),
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
    *,
    quality_gate_ids: list[str] | None = None,
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
        quality_gates=derive_quality_gates(_gate_ids_or_default(quality_gate_ids), []),
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
        quality_gates=derive_quality_gates(_gate_ids_or_default(quality_gate_ids), criteria_ids),
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


def create_parallel_plan(
    spec: SpecificationData,
    base_commit: str,
    reasoning: list[str],
    snapshot: RepositorySnapshotData | None = None,
    *,
    quality_gate_ids: list[str] | None = None,
) -> ExecutionPlanData:
    criteria_ids = [
        criterion.id
        for criterion in spec.acceptance_criteria
        if criterion.priority == "required"
    ]
    del snapshot
    objective = spec.objective.lower()
    safe_docs_examples = (
        ("文档" in objective and "示例" in objective)
        or ("docs" in objective and "examples" in objective)
    )
    first_paths = ["docs/**"] if safe_docs_examples else ["src/**"]
    second_paths = ["examples/**"] if safe_docs_examples else ["src/coductor/**"]
    first_task = PlanTask(
        id="T001",
        title="并行完成第一组独立变更",
        task_type=TaskType.INTEGRATED_IMPLEMENTATION,
        role="builder",
        depends_on=[],
        consumes=["02_spec.yaml", "01_repository_snapshot.yaml"],
        produces=["tasks/T001/worker_result.yaml"],
        allowed_paths=first_paths,
        forbidden_paths=[".env*", "**/secrets/**", "**/production/**"],
        acceptance_criteria=[],
        quality_gates=derive_quality_gates(_gate_ids_or_default(quality_gate_ids), []),
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )
    second_task = PlanTask(
        id="T002",
        title="并行完成第二组独立变更",
        task_type=TaskType.INTEGRATED_IMPLEMENTATION,
        role="builder",
        depends_on=[],
        consumes=["02_spec.yaml", "01_repository_snapshot.yaml"],
        produces=["tasks/T002/worker_result.yaml"],
        allowed_paths=second_paths,
        forbidden_paths=[".env*", "**/secrets/**", "**/production/**"],
        acceptance_criteria=criteria_ids,
        quality_gates=derive_quality_gates(_gate_ids_or_default(quality_gate_ids), criteria_ids),
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.PARALLEL,
        strategy_reasoning=[
            *reasoning,
            "并行候选任务必须声明互不重叠的 allowed_paths",
            "并行批次不允许在同一批内生产并消费契约",
        ],
        base_commit=base_commit,
        tasks=[first_task, second_task],
        graph={"edges": []},
    )
    plan.validation = PlanValidator(
        acceptance_criteria=spec.acceptance_criteria,
        produced_artifacts={
            "02_spec.yaml",
            "01_repository_snapshot.yaml",
            "tasks/T001/worker_result.yaml",
            "tasks/T002/worker_result.yaml",
        },
    ).validate(plan)
    return plan


def _gate_ids_or_default(quality_gate_ids: list[str] | None) -> list[str]:
    return ["unit_tests"] if quality_gate_ids is None else quality_gate_ids
