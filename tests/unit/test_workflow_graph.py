from __future__ import annotations

from coductor.domain.enums import RunStatus
from coductor.workflow.graph import WORKFLOW_NODES, build_workflow_graph, compile_workflow_graph
from coductor.workflow.langgraph_checkpoint import langgraph_thread_config
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
    assert result["artifacts"]["00_goal"] == "00_goal.yaml"
    assert result["artifacts"]["07_evidence"] == "07_evidence.yaml"


def test_compile_workflow_graph_accepts_optional_checkpointer(monkeypatch) -> None:
    graph = build_workflow_graph()
    checkpointer = object()
    calls: list[object] = []

    def recording_compile(*, checkpointer=None):
        calls.append(checkpointer)
        return "compiled"

    monkeypatch.setattr(graph, "compile", recording_compile)

    compiled = compile_workflow_graph(graph=graph, checkpointer=checkpointer)

    assert compiled == "compiled"
    assert calls == [checkpointer]
    assert langgraph_thread_config("run_abc") == {"configurable": {"thread_id": "run_abc"}}


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
