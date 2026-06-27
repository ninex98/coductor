"""Task execution node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, ExecutionPlanData
from coductor.contracts.repository import ContractRepository
from coductor.domain.enums import ArtifactType, ExecutionStrategy, RunStatus
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


def dispatch_next_stage(state: WorkflowState) -> str:
    return "__end__" if state.status == RunStatus.HUMAN_REQUIRED else "integrate_changes"


def materialize_tasks_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
) -> dict[str, Any]:
    if context is not None:
        state.current_stage = "materialize_tasks"
        context.save(state)
    return {"current_stage": "materialize_tasks"}


def dispatch_tasks_node(
    state: WorkflowState,
    *,
    context: WorkflowRuntimeContext | None = None,
) -> dict[str, Any]:
    if context is not None:
        state.current_stage = "dispatch_tasks"
        if context.task_execution is None:
            context.save(state)
            return {"current_stage": "dispatch_tasks"}
        plan = ArtifactEnvelope[ExecutionPlanData].model_validate(
            context.repo.read(
                "03_execution_plan.yaml",
                ArtifactType.EXECUTION_PLAN,
            ).model_dump(mode="json")
        )

        def record_dispatch(task_id: str, _worker_handle: object) -> None:
            if context.on_dispatch is not None:
                context.on_dispatch(task_id)
            if plan.data.strategy == ExecutionStrategy.PARALLEL:
                return
            state.artifacts[f"task_{task_id}"] = f"tasks/{task_id}/task.yaml"
            context.save(state)
            state.artifacts[f"worker_result_{task_id}"] = (
                f"tasks/{task_id}/worker_result.yaml"
            )
            context.save(state)

        if plan.data.strategy == ExecutionStrategy.PARALLEL:
            executed_tasks = context.task_execution.execute_plan_tasks(
                context.repo,
                state.run_id,
                plan,
                on_dispatch=record_dispatch,
                skip_task_ids=set(state.completed_task_ids),
            )
            failed_task_ids = context.task_execution.failed_task_ids(
                context.repo,
                [task.task_id for task in executed_tasks],
            )
            if failed_task_ids:
                state.status = RunStatus.HUMAN_REQUIRED
                state.current_stage = "human_required"
                state.last_error = f"worker failed: {', '.join(failed_task_ids)}"
                context.save(state)
                return {
                    "current_stage": state.current_stage,
                    "status": state.status,
                    "last_error": state.last_error,
                    "artifacts": state.artifacts,
                }
            for executed_task in executed_tasks:
                state.artifacts[f"task_{executed_task.task_id}"] = (
                    f"tasks/{executed_task.task_id}/task.yaml"
                )
                state.artifacts[f"worker_result_{executed_task.task_id}"] = (
                    f"tasks/{executed_task.task_id}/worker_result.yaml"
                )
                if executed_task.task_id not in state.completed_task_ids:
                    state.completed_task_ids.append(executed_task.task_id)
            context.save(state)
            return {
                "current_stage": state.current_stage,
                "status": state.status,
                "last_error": state.last_error,
                "artifacts": state.artifacts,
                "completed_task_ids": state.completed_task_ids,
            }

        contracts = {}
        contract_repository = ContractRepository(context.repo.root)
        for plan_task in context.task_execution.tasks_in_dependency_order(plan.data.tasks):
            if plan_task.id in state.completed_task_ids:
                for contract in contract_repository.load_manifest():
                    if contract.producer_task_id == plan_task.id:
                        contracts[contract.path] = contract
                continue
            executed_task = context.task_execution.execute_plan_task(
                context.repo,
                state.run_id,
                plan,
                plan_task,
                contracts,
                on_dispatch=record_dispatch,
            )
            failed_task_ids = context.task_execution.failed_task_ids(
                context.repo,
                [executed_task.task_id],
            )
            if failed_task_ids:
                state.status = RunStatus.HUMAN_REQUIRED
                state.current_stage = "human_required"
                state.last_error = f"worker failed: {', '.join(failed_task_ids)}"
                context.save(state)
                return {
                    "current_stage": state.current_stage,
                    "status": state.status,
                    "last_error": state.last_error,
                    "artifacts": state.artifacts,
                }
            if executed_task.task_id not in state.completed_task_ids:
                state.completed_task_ids.append(executed_task.task_id)
                context.save(state)
            contracts.update(executed_task.produced_contracts)
        context.save(state)
        return {
            "current_stage": state.current_stage,
            "status": state.status,
            "last_error": state.last_error,
            "artifacts": state.artifacts,
            "completed_task_ids": state.completed_task_ids,
        }
    return {"current_stage": "dispatch_tasks"}
