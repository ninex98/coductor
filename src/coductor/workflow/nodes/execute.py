"""Task execution node helpers."""

from __future__ import annotations

from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, ExecutionPlanData
from coductor.domain.enums import ArtifactType
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState


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
            state.artifacts[f"task_{task_id}"] = f"tasks/{task_id}/task.yaml"
            context.save(state)
            state.artifacts[f"worker_result_{task_id}"] = (
                f"tasks/{task_id}/worker_result.yaml"
            )
            context.save(state)

        context.task_execution.execute_plan_tasks(
            context.repo,
            state.run_id,
            plan,
            on_dispatch=record_dispatch,
        )
        context.save(state)
        return {
            "current_stage": "dispatch_tasks",
            "artifacts": state.artifacts,
        }
    return {"current_stage": "dispatch_tasks"}
