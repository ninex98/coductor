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
