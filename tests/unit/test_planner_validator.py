from __future__ import annotations

from coductor.artifacts.models import AcceptanceCriterion, ExecutionPlanData, PlanTask
from coductor.domain.enums import ExecutionStrategy, SandboxMode, TaskType, VerificationType
from coductor.planning.validator import PlanValidator


def _task(
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    allowed_paths: list[str] | None = None,
) -> PlanTask:
    return PlanTask(
        id=task_id,
        title=f"Task {task_id}",
        task_type=TaskType.INTEGRATED_IMPLEMENTATION,
        role="builder",
        depends_on=depends_on or [],
        consumes=["02_spec.yaml"],
        produces=[f"tasks/{task_id}/worker_result.yaml"],
        allowed_paths=allowed_paths or ["src/**"],
        forbidden_paths=[],
        acceptance_criteria=["AC001"],
        quality_gates=["unit_tests"],
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )


def test_rejects_dependency_cycle() -> None:
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.SOLO,
        strategy_reasoning=["修改集中且高度耦合，单一上下文成本更低"],
        base_commit="abc123",
        tasks=[
            _task("T001", depends_on=["T002"]),
            _task("T002", depends_on=["T001"]),
        ],
        graph={"edges": [["T001", "T002"], ["T002", "T001"]]},
    )

    result = PlanValidator(
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC001",
                statement="行为正确",
                verification=VerificationType.AUTOMATED,
                priority="required",
            )
        ],
        produced_artifacts={"02_spec.yaml"},
    ).validate(plan)

    assert not result.valid
    assert any("cycle" in error for error in result.errors)


def test_requires_acceptance_coverage() -> None:
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.SOLO,
        strategy_reasoning=["修改集中且高度耦合，单一上下文成本更低"],
        base_commit="abc123",
        tasks=[_task("T001")],
        graph={"edges": []},
    )

    result = PlanValidator(
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC001",
                statement="行为正确",
                verification=VerificationType.AUTOMATED,
                priority="required",
            ),
            AcceptanceCriterion(
                id="AC002",
                statement="报告完整",
                verification=VerificationType.AUTOMATED,
                priority="required",
            ),
        ],
        produced_artifacts={"02_spec.yaml"},
    ).validate(plan)

    assert not result.valid
    assert "AC002" in "\n".join(result.errors)


def test_parallel_path_overlap_is_rejected() -> None:
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.PARALLEL,
        strategy_reasoning=["两个任务可并行"],
        base_commit="abc123",
        tasks=[
            _task("T001", allowed_paths=["src/coductor/**"]),
            _task("T002", allowed_paths=["src/coductor/workflow/**"]),
        ],
        graph={"edges": []},
    )

    result = PlanValidator(
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC001",
                statement="行为正确",
                verification=VerificationType.AUTOMATED,
                priority="required",
            )
        ],
        produced_artifacts={"02_spec.yaml"},
    ).validate(plan)

    assert not result.valid
    assert any("overlap" in error for error in result.errors)
