"""Task execution node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, ExecutionPlanData
from coductor.contracts.models import ContractArtifact
from coductor.domain.enums import ArtifactType, RunStatus
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
            state.artifacts[f"task_{task_id}"] = f"tasks/{task_id}/task.yaml"
            context.save(state)
            state.artifacts[f"worker_result_{task_id}"] = (
                f"tasks/{task_id}/worker_result.yaml"
            )
            context.save(state)

        contracts: dict[str, ContractArtifact] = {}
        for plan_task in context.task_execution.tasks_in_dependency_order(plan.data.tasks):
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
