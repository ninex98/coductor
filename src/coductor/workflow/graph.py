"""LangGraph workflow graph boundaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from coductor.domain.enums import RunStatus
from coductor.workflow.state import WorkflowState

WORKFLOW_NODES = [
    "collect_goal",
    "inspect_repository",
    "draft_spec",
    "validate_spec",
    "create_execution_plan",
    "validate_execution_plan",
    "materialize_tasks",
    "dispatch_tasks",
    "integrate_changes",
    "run_quality_gates",
    "repair_failure",
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


def _prepare_evidence_node(state: WorkflowState) -> NodePatch:
    status = (
        RunStatus.READY_FOR_HUMAN_REVIEW
        if state.status == RunStatus.RUNNING
        else state.status
    )
    return {"current_stage": "prepare_evidence", "status": status}


def _run_quality_gates_node(state: WorkflowState) -> NodePatch:
    return {"current_stage": "run_quality_gates"}


def _repair_failure_node(state: WorkflowState) -> NodePatch:
    return {
        "current_stage": "repair_failure",
        "repair_attempts": state.repair_attempts + 1,
        "gate_passed": True,
    }


def _run_independent_review_node(state: WorkflowState) -> NodePatch:
    return {"current_stage": "run_independent_review"}


def _route_after_gates(state: WorkflowState) -> str:
    if state.gate_passed:
        return "run_independent_review"
    if state.repair_attempts < state.max_repair_attempts:
        return "repair_failure"
    return "prepare_evidence"


def _route_after_review(state: WorkflowState) -> str:
    return "prepare_evidence" if state.review_passed else "repair_failure"


def build_workflow_graph() -> StateGraph[WorkflowState]:
    graph = StateGraph(WorkflowState)
    _add_node(graph, "collect_goal", _stage_node("collect_goal"))
    _add_node(graph, "inspect_repository", _stage_node("inspect_repository"))
    _add_node(graph, "draft_spec", _stage_node("draft_spec"))
    _add_node(graph, "validate_spec", _stage_node("validate_spec"))
    _add_node(graph, "create_execution_plan", _stage_node("create_execution_plan"))
    _add_node(graph, "validate_execution_plan", _stage_node("validate_execution_plan"))
    _add_node(graph, "materialize_tasks", _stage_node("materialize_tasks"))
    _add_node(graph, "dispatch_tasks", _stage_node("dispatch_tasks"))
    _add_node(graph, "integrate_changes", _stage_node("integrate_changes"))
    _add_node(graph, "run_quality_gates", _run_quality_gates_node)
    _add_node(graph, "repair_failure", _repair_failure_node)
    _add_node(graph, "run_independent_review", _run_independent_review_node)
    _add_node(graph, "prepare_evidence", _prepare_evidence_node)

    graph.add_edge(START, "collect_goal")
    graph.add_edge("collect_goal", "inspect_repository")
    graph.add_edge("inspect_repository", "draft_spec")
    graph.add_edge("draft_spec", "validate_spec")
    graph.add_edge("validate_spec", "create_execution_plan")
    graph.add_edge("create_execution_plan", "validate_execution_plan")
    graph.add_edge("validate_execution_plan", "materialize_tasks")
    graph.add_edge("materialize_tasks", "dispatch_tasks")
    graph.add_edge("dispatch_tasks", "integrate_changes")
    graph.add_edge("integrate_changes", "run_quality_gates")
    graph.add_conditional_edges("run_quality_gates", _route_after_gates)
    graph.add_edge("repair_failure", "run_quality_gates")
    graph.add_conditional_edges("run_independent_review", _route_after_review)
    graph.add_edge("prepare_evidence", END)
    return graph


def _add_node(
    graph: StateGraph[WorkflowState],
    name: str,
    action: Callable[[WorkflowState], NodePatch],
) -> None:
    # LangGraph accepts state-patch callables at runtime; its overloads are
    # intentionally broad and currently too complex for mypy to infer here.
    graph.add_node(name, action)  # type: ignore[call-overload]
