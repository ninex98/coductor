"""LangGraph workflow graph boundaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from coductor.artifacts.models import (
    ArtifactEnvelope,
    ExecutionPlanData,
    GateReportData,
    GoalData,
    GoalSatisfactionReportData,
    RepositorySnapshotData,
    ReviewReportData,
    SpecificationData,
    WorkerResultData,
)
from coductor.backends.base import WorkerHandle
from coductor.domain.enums import ArtifactType, ExecutionMode, ExecutionStrategy, RunStatus
from coductor.workflow.nodes.deliver import prepare_evidence_node
from coductor.workflow.nodes.execute import (
    dispatch_next_stage,
    dispatch_tasks_node,
    materialize_tasks_node,
)
from coductor.workflow.nodes.inspect import inspect_repository_node
from coductor.workflow.nodes.intake import collect_goal_node
from coductor.workflow.nodes.integrate import integrate_changes_node
from coductor.workflow.nodes.plan import create_execution_plan_node
from coductor.workflow.nodes.repair import repair_failure_node
from coductor.workflow.nodes.review import run_independent_review_node
from coductor.workflow.nodes.satisfaction import evaluate_goal_satisfaction_node
from coductor.workflow.nodes.specify import draft_spec_node
from coductor.workflow.nodes.verification_plan import create_verification_plan_node
from coductor.workflow.nodes.verify import run_quality_gates_node
from coductor.workflow.runtime import WorkflowRuntimeContext
from coductor.workflow.state import WorkflowState

WORKFLOW_NODES = [
    "collect_goal",
    "inspect_repository",
    "draft_spec",
    "validate_spec",
    "create_verification_plan",
    "create_execution_plan",
    "validate_execution_plan",
    "materialize_tasks",
    "dispatch_tasks",
    "integrate_changes",
    "run_quality_gates",
    "repair_failure",
    "evaluate_goal_satisfaction",
    "run_independent_review",
    "prepare_evidence",
]


def describe_graph() -> list[str]:
    return WORKFLOW_NODES.copy()


NodePatch = dict[str, Any]


def _stage_node(stage: str) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        return {"current_stage": stage}

    return node


def _route_after_gates(state: WorkflowState) -> str:
    if state.status == RunStatus.HUMAN_REQUIRED:
        return END
    if state.gate_passed:
        return "evaluate_goal_satisfaction"
    if state.repair_attempts < state.max_repair_attempts:
        return "repair_failure"
    return "prepare_evidence"


def _route_after_plan_validation(state: WorkflowState) -> str:
    return END if state.status == RunStatus.HUMAN_REQUIRED else "materialize_tasks"


def _route_after_spec_validation(state: WorkflowState) -> str:
    return END if state.status == RunStatus.HUMAN_REQUIRED else "create_verification_plan"


def _route_after_review(state: WorkflowState) -> str:
    del state
    return "prepare_evidence"


def _route_after_goal_satisfaction(state: WorkflowState) -> str:
    if state.goal_satisfied:
        return "run_independent_review"
    if state.satisfaction_repair_attempts < state.max_repair_attempts:
        return "repair_failure"
    return "run_independent_review"


def _route_after_review_with_context(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], str]:
    def route(state: WorkflowState) -> str:
        if (
            context.config is not None
            and context.config.workflow.repair_after_blocking_review
            and not state.review_passed
            and state.repair_attempts < state.max_repair_attempts
        ):
            return "repair_failure"
        return "prepare_evidence"

    return route


def _entry_node(state: WorkflowState) -> str:
    if state.current_stage in WORKFLOW_NODES:
        return state.current_stage
    if state.current_stage == "human_required":
        return END
    return "collect_goal"


def build_workflow_graph(
    *,
    context: WorkflowRuntimeContext | None = None,
) -> StateGraph[WorkflowState]:
    graph = StateGraph(WorkflowState)
    _add_node(
        graph,
        "collect_goal",
        _with_context(collect_goal_node, context) if context is not None else collect_goal_node,
    )
    _add_node(
        graph,
        "inspect_repository",
        _contextual_inspect_node(context) if context is not None else inspect_repository_node,
    )
    _add_node(
        graph,
        "draft_spec",
        _contextual_spec_node(context) if context is not None else draft_spec_node,
    )
    _add_node(graph, "validate_spec", _stage_node("validate_spec"))
    _add_node(
        graph,
        "create_verification_plan",
        (
            _contextual_verification_plan_node(context)
            if context is not None
            else create_verification_plan_node
        ),
    )
    _add_node(
        graph,
        "create_execution_plan",
        (
            _contextual_plan_node(context)
            if context is not None
            else create_execution_plan_node
        ),
    )
    _add_node(graph, "validate_execution_plan", _stage_node("validate_execution_plan"))
    _add_node(
        graph,
        "materialize_tasks",
        (
            _with_context(materialize_tasks_node, context)
            if context is not None
            else materialize_tasks_node
        ),
    )
    _add_node(
        graph,
        "dispatch_tasks",
        (
            _with_context(dispatch_tasks_node, context)
            if context is not None
            else dispatch_tasks_node
        ),
    )
    _add_node(
        graph,
        "integrate_changes",
        (
            _contextual_integrate_node(context)
            if context is not None and context.verification is not None
            else integrate_changes_node
        ),
    )
    _add_node(
        graph,
        "run_quality_gates",
        (
            _contextual_quality_gates_node(context)
            if context is not None and context.verification is not None
            else run_quality_gates_node
        ),
    )
    _add_node(
        graph,
        "repair_failure",
        (
            _contextual_repair_node(context)
            if context is not None and context.repair is not None
            else repair_failure_node
        ),
    )
    _add_node(
        graph,
        "evaluate_goal_satisfaction",
        (
            _with_context(evaluate_goal_satisfaction_node, context)
            if context is not None and context.verification is not None
            else evaluate_goal_satisfaction_node
        ),
    )
    _add_node(
        graph,
        "run_independent_review",
        (
            _contextual_review_node(context)
            if context is not None and context.review_delivery is not None
            else run_independent_review_node
        ),
    )
    _add_node(
        graph,
        "prepare_evidence",
        (
            _contextual_evidence_node(context)
            if context is not None and context.review_delivery is not None
            else prepare_evidence_node
        ),
    )

    graph.add_conditional_edges(START, _entry_node)
    graph.add_edge("collect_goal", "inspect_repository")
    graph.add_edge("inspect_repository", "draft_spec")
    graph.add_edge("draft_spec", "validate_spec")
    graph.add_conditional_edges("validate_spec", _route_after_spec_validation)
    graph.add_edge("create_verification_plan", "create_execution_plan")
    graph.add_edge("create_execution_plan", "validate_execution_plan")
    graph.add_conditional_edges("validate_execution_plan", _route_after_plan_validation)
    graph.add_edge("materialize_tasks", "dispatch_tasks")
    graph.add_conditional_edges("dispatch_tasks", dispatch_next_stage)
    graph.add_edge("integrate_changes", "run_quality_gates")
    graph.add_conditional_edges("run_quality_gates", _route_after_gates)
    graph.add_edge("repair_failure", "run_quality_gates")
    graph.add_conditional_edges("evaluate_goal_satisfaction", _route_after_goal_satisfaction)
    graph.add_conditional_edges(
        "run_independent_review",
        _route_after_review_with_context(context) if context is not None else _route_after_review,
    )
    graph.add_edge("prepare_evidence", END)
    return graph


def compile_workflow_graph(
    *,
    graph: StateGraph[WorkflowState] | None = None,
    checkpointer: Any | None = None,
) -> Any:
    workflow = graph or build_workflow_graph()
    return workflow.compile(checkpointer=checkpointer)


def _add_node(
    graph: StateGraph[WorkflowState],
    name: str,
    action: Callable[[WorkflowState], NodePatch],
) -> None:
    # LangGraph accepts state-patch callables at runtime; its overloads are
    # intentionally broad and currently too complex for mypy to infer here.
    graph.add_node(name, action)  # type: ignore[call-overload]


def _with_context(
    action: Callable[..., NodePatch],
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        return action(state, context=context)

    return node


def _contextual_inspect_node(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        goal = ArtifactEnvelope[GoalData].model_validate(
            context.repo.read("00_goal.yaml", ArtifactType.GOAL).model_dump(mode="json")
        )
        return inspect_repository_node(state, context=context, goal=goal)

    return node


def _contextual_spec_node(context: WorkflowRuntimeContext) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        goal = ArtifactEnvelope[GoalData].model_validate(
            context.repo.read("00_goal.yaml", ArtifactType.GOAL).model_dump(mode="json")
        )
        snapshot = ArtifactEnvelope[RepositorySnapshotData].model_validate(
            context.repo.read(
                "01_repository_snapshot.yaml",
                ArtifactType.REPOSITORY_SNAPSHOT,
            ).model_dump(mode="json")
        )
        return draft_spec_node(state, context=context, goal=goal, snapshot=snapshot)

    return node


def _contextual_plan_node(context: WorkflowRuntimeContext) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        snapshot = ArtifactEnvelope[RepositorySnapshotData].model_validate(
            context.repo.read(
                "01_repository_snapshot.yaml",
                ArtifactType.REPOSITORY_SNAPSHOT,
            ).model_dump(mode="json")
        )
        spec = ArtifactEnvelope[SpecificationData].model_validate(
            context.repo.read("02_spec.yaml", ArtifactType.SPECIFICATION).model_dump(mode="json")
        )
        return create_execution_plan_node(
            state,
            context=context,
            spec=spec,
            snapshot=snapshot,
            requested_mode=ExecutionMode(state.requested_mode),
        )

    return node


def _contextual_verification_plan_node(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        spec = ArtifactEnvelope[SpecificationData].model_validate(
            context.repo.read("02_spec.yaml", ArtifactType.SPECIFICATION).model_dump(mode="json")
        )
        return create_verification_plan_node(state, context=context, spec=spec)

    return node


def _contextual_integrate_node(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        if context.verification is None:
            raise ValueError("integrate_changes node requires verification service")
        plan = _read_execution_plan(context)
        return integrate_changes_node(
            state,
            context=context,
            plan=plan,
            completed_task_ids=_completed_task_ids(state),
            verification=context.verification,
        )

    return node


def _contextual_quality_gates_node(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        if context.verification is None:
            raise ValueError("run_quality_gates node requires verification service")
        return run_quality_gates_node(
            state,
            context=context,
            verification=context.verification,
        )

    return node


def _contextual_repair_node(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        repair = context.repair
        if repair is None:
            raise ValueError("repair_failure node requires repair service")
        completed_task_ids = _completed_task_ids(state)
        if not completed_task_ids:
            raise ValueError("repair_failure node requires a completed worker result")
        target_task_id = completed_task_ids[-1]
        worker_result = ArtifactEnvelope[WorkerResultData].model_validate(
            context.repo.read(
                f"tasks/{target_task_id}/worker_result.yaml",
                ArtifactType.WORKER_RESULT,
            ).model_dump(mode="json")
        )
        gate_report = ArtifactEnvelope[GateReportData].model_validate(
            context.repo.read(
                "05_gate_report.yaml",
                ArtifactType.GATE_REPORT,
            ).model_dump(mode="json")
        )
        goal_satisfaction = None
        if (context.repo.root / "07_goal_satisfaction.yaml").exists() and not state.goal_satisfied:
            goal_satisfaction = ArtifactEnvelope[GoalSatisfactionReportData].model_validate(
                context.repo.read(
                    "07_goal_satisfaction.yaml",
                    ArtifactType.GOAL_SATISFACTION_REPORT,
                ).model_dump(mode="json")
            )
        return repair_failure_node(
            state,
            context=context,
            builder_handle=WorkerHandle(
                worker_id=worker_result.data.worker_id,
                thread_id=worker_result.data.thread_id,
            ),
            gate_report=gate_report,
            repair=repair,
            target_task_id=target_task_id,
            goal_satisfaction=goal_satisfaction,
        )

    return node


def _contextual_review_node(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        review_delivery = context.review_delivery
        if review_delivery is None:
            raise ValueError("run_independent_review node requires review delivery service")
        gate_report = ArtifactEnvelope[GateReportData].model_validate(
            context.repo.read(
                "05_gate_report.yaml",
                ArtifactType.GATE_REPORT,
            ).model_dump(mode="json")
        )
        return run_independent_review_node(
            state,
            context=context,
            review=lambda: (
                context.review_callback(
                    gate_report,
                    _completed_task_ids(state),
                    state,
                )
                if context.review_callback is not None
                else review_delivery.review(
                    context.repo,
                    state.run_id,
                    gate_report,
                    _completed_task_ids(state),
                )
            ),
        )

    return node


def _contextual_evidence_node(
    context: WorkflowRuntimeContext,
) -> Callable[[WorkflowState], NodePatch]:
    def node(state: WorkflowState) -> NodePatch:
        review_delivery = context.review_delivery
        if review_delivery is None:
            raise ValueError("prepare_evidence node requires review delivery service")
        goal = ArtifactEnvelope[GoalData].model_validate(
            context.repo.read("00_goal.yaml", ArtifactType.GOAL).model_dump(mode="json")
        )
        plan = _read_execution_plan(context)
        gate_report = ArtifactEnvelope[GateReportData].model_validate(
            context.repo.read(
                "05_gate_report.yaml",
                ArtifactType.GATE_REPORT,
            ).model_dump(mode="json")
        )
        review = ArtifactEnvelope[ReviewReportData].model_validate(
            context.repo.read(
                "06_review.yaml",
                ArtifactType.REVIEW_REPORT,
            ).model_dump(mode="json")
        )
        return prepare_evidence_node(
            state,
            context=context,
            evidence=lambda: (
                context.evidence_callback(
                    goal,
                    gate_report,
                    review,
                    ExecutionStrategy(plan.data.strategy),
                    _completed_task_ids(state),
                    state,
                )
                if context.evidence_callback is not None
                else review_delivery.evidence(
                    context.repo,
                    state.run_id,
                    goal,
                    gate_report,
                    review,
                    ExecutionStrategy(plan.data.strategy),
                    _completed_task_ids(state),
                )
            ),
        )

    return node


def _read_execution_plan(
    context: WorkflowRuntimeContext,
) -> ArtifactEnvelope[ExecutionPlanData]:
    return ArtifactEnvelope[ExecutionPlanData].model_validate(
        context.repo.read(
            "03_execution_plan.yaml",
            ArtifactType.EXECUTION_PLAN,
        ).model_dump(mode="json")
    )


def _completed_task_ids(state: WorkflowState) -> list[str]:
    if state.completed_task_ids:
        return state.completed_task_ids.copy()
    prefix = "worker_result_"
    return sorted(
        key.removeprefix(prefix)
        for key in state.artifacts
        if key.startswith(prefix)
    )
