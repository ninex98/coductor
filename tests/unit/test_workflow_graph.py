from __future__ import annotations

from coductor.domain.enums import RunStatus
from coductor.workflow.graph import WORKFLOW_NODES, build_workflow_graph
from coductor.workflow.state import WorkflowState


def test_build_workflow_graph_contains_expected_nodes() -> None:
    graph = build_workflow_graph()

    assert set(WORKFLOW_NODES).issubset(set(graph.nodes))


def test_compiled_workflow_graph_can_advance_state() -> None:
    compiled = build_workflow_graph().compile()

    result = compiled.invoke(
        WorkflowState(
            run_id="run_graph_000000000000000000001",
            status=RunStatus.RUNNING,
            raw_goal="只验证图状态",
        )
    )

    assert result["current_stage"] == "prepare_evidence"
    assert result["status"] == RunStatus.READY_FOR_HUMAN_REVIEW


def test_workflow_graph_routes_gate_failure_through_repair() -> None:
    compiled = build_workflow_graph().compile()

    result = compiled.invoke(
        WorkflowState(
            run_id="run_graph_000000000000000000002",
            status=RunStatus.RUNNING,
            raw_goal="只验证修复路由",
            gate_passed=False,
            max_repair_attempts=1,
        )
    )

    assert result["repair_attempts"] == 1
    assert result["gate_passed"] is True
    assert result["current_stage"] == "prepare_evidence"
