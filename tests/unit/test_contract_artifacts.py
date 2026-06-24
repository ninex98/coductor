from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import AcceptanceCriterion, ExecutionPlanData, PlanTask
from coductor.contracts.models import ContractArtifact
from coductor.contracts.repository import ContractRepository
from coductor.domain.enums import ExecutionStrategy, SandboxMode, TaskType, VerificationType
from coductor.planning.validator import PlanValidator


def _task(
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    allowed_paths: list[str] | None = None,
    consumes: list[str] | None = None,
    produces: list[str] | None = None,
) -> PlanTask:
    return PlanTask(
        id=task_id,
        title=f"Task {task_id}",
        task_type=TaskType.INTEGRATED_IMPLEMENTATION,
        role="builder",
        depends_on=depends_on or [],
        consumes=consumes or ["02_spec.yaml"],
        produces=produces or [f"tasks/{task_id}/worker_result.yaml"],
        allowed_paths=allowed_paths or ["src/**"],
        forbidden_paths=[],
        acceptance_criteria=["AC001"],
        quality_gates=["unit_tests"],
        sandbox=SandboxMode.WORKSPACE_WRITE,
    )


def _criterion() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id="AC001",
        statement="行为正确",
        verification=VerificationType.AUTOMATED,
        priority="required",
    )


def test_contract_file_hash_is_recorded_in_downstream_task(tmp_path: Path) -> None:
    contract_path = tmp_path / "contracts/api.schema.json"
    contract_path.parent.mkdir()
    contract_path.write_text('{"type":"object"}', encoding="utf-8")
    repository = ContractRepository(tmp_path)

    contract = repository.record(
        "contracts/api.schema.json",
        kind="json_schema",
        producer_task_id="T001",
    )
    task = _task("T002", consumes=[contract.path], depends_on=["T001"])

    assert isinstance(contract, ContractArtifact)
    assert contract.path in task.consumes
    assert contract.sha256
    assert contract.producer_task_id == "T001"


def test_plan_validator_rejects_contract_consumer_without_producer() -> None:
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.PIPELINE,
        strategy_reasoning=["需要稳定契约", "下游消费契约"],
        base_commit="abc123",
        tasks=[
            _task("T001"),
            _task(
                "T002",
                depends_on=["T001"],
                consumes=["contracts/api.schema.json"],
            ),
        ],
        graph={"edges": [["T001", "T002"]]},
    )

    result = PlanValidator(
        acceptance_criteria=[_criterion()],
        produced_artifacts={"02_spec.yaml", "tasks/T001/worker_result.yaml"},
    ).validate(plan)

    assert not result.valid
    assert any("contract" in error for error in result.errors)


def test_plan_validator_allows_contract_consumer_with_upstream_producer() -> None:
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.PIPELINE,
        strategy_reasoning=["需要稳定契约", "下游消费契约"],
        base_commit="abc123",
        tasks=[
            _task(
                "T001",
                produces=[
                    "tasks/T001/worker_result.yaml",
                    "contracts/api.schema.json",
                ],
            ),
            _task(
                "T002",
                depends_on=["T001"],
                consumes=["contracts/api.schema.json"],
            ),
        ],
        graph={"edges": [["T001", "T002"]]},
    )

    result = PlanValidator(
        acceptance_criteria=[_criterion()],
        produced_artifacts={
            "02_spec.yaml",
            "tasks/T001/worker_result.yaml",
            "contracts/api.schema.json",
        },
    ).validate(plan)

    assert result.valid


def test_parallel_plan_rejects_contract_handoff_inside_parallel_batch() -> None:
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.PARALLEL,
        strategy_reasoning=["两个任务看似可并行", "但契约必须先冻结"],
        base_commit="abc123",
        tasks=[
            _task(
                "T001",
                allowed_paths=["contracts/**"],
                produces=["contracts/api.schema.json"],
            ),
            _task(
                "T002",
                allowed_paths=["src/**"],
                consumes=["contracts/api.schema.json"],
            ),
        ],
        graph={"edges": []},
    )

    result = PlanValidator(
        acceptance_criteria=[_criterion()],
        produced_artifacts={"02_spec.yaml", "contracts/api.schema.json"},
    ).validate(plan)

    assert not result.valid
    assert any("parallel contract" in error for error in result.errors)


def test_parallel_plan_rejects_duplicate_contract_writers() -> None:
    plan = ExecutionPlanData(
        strategy=ExecutionStrategy.PARALLEL,
        strategy_reasoning=["两个任务看似可并行", "但契约路径不能冲突"],
        base_commit="abc123",
        tasks=[
            _task(
                "T001",
                allowed_paths=["contracts/api/**"],
                produces=["contracts/api.schema.json"],
            ),
            _task(
                "T002",
                allowed_paths=["contracts/other/**"],
                produces=["contracts/api.schema.json"],
            ),
        ],
        graph={"edges": []},
    )

    result = PlanValidator(
        acceptance_criteria=[_criterion()],
        produced_artifacts={"02_spec.yaml", "contracts/api.schema.json"},
    ).validate(plan)

    assert not result.valid
    assert any("parallel contract" in error for error in result.errors)
