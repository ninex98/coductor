from __future__ import annotations

from coductor.workflow.nodes.inspect import inspect_repository_node
from coductor.workflow.nodes.intake import collect_goal_node
from coductor.workflow.nodes.plan import create_execution_plan_node
from coductor.workflow.nodes.specify import draft_spec_node
from coductor.workflow.state import WorkflowState


def test_front_half_nodes_record_stage_and_artifact_paths() -> None:
    state = WorkflowState(run_id="run_abc", raw_goal="修复示例函数")

    patches = [
        collect_goal_node(state),
        inspect_repository_node(state),
        draft_spec_node(state),
        create_execution_plan_node(state),
    ]

    assert patches == [
        {"current_stage": "collect_goal", "artifacts": {"00_goal": "00_goal.yaml"}},
        {
            "current_stage": "inspect_repository",
            "artifacts": {"01_repository_snapshot": "01_repository_snapshot.yaml"},
        },
        {"current_stage": "draft_spec", "artifacts": {"02_spec": "02_spec.yaml"}},
        {
            "current_stage": "create_execution_plan",
            "artifacts": {"03_execution_plan": "03_execution_plan.yaml"},
        },
    ]
