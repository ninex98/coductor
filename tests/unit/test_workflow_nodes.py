from __future__ import annotations

from coductor.domain.enums import RunStatus
from coductor.workflow.nodes.deliver import prepare_evidence_node
from coductor.workflow.nodes.execute import dispatch_tasks_node, materialize_tasks_node
from coductor.workflow.nodes.inspect import inspect_repository_node
from coductor.workflow.nodes.intake import collect_goal_node
from coductor.workflow.nodes.integrate import integrate_changes_node
from coductor.workflow.nodes.plan import create_execution_plan_node
from coductor.workflow.nodes.repair import repair_failure_node
from coductor.workflow.nodes.review import run_independent_review_node
from coductor.workflow.nodes.specify import draft_spec_node
from coductor.workflow.nodes.verify import run_quality_gates_node
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


def test_back_half_nodes_record_stage_and_artifact_paths() -> None:
    state = WorkflowState(run_id="run_abc", raw_goal="修复示例函数")

    patches = [
        materialize_tasks_node(state),
        dispatch_tasks_node(state),
        integrate_changes_node(state),
        run_quality_gates_node(state),
        repair_failure_node(state),
        run_independent_review_node(state),
        prepare_evidence_node(state),
    ]

    assert patches == [
        {"current_stage": "materialize_tasks"},
        {"current_stage": "dispatch_tasks"},
        {
            "current_stage": "integrate_changes",
            "artifacts": {"04_integration": "04_integration.yaml"},
        },
        {
            "current_stage": "run_quality_gates",
            "artifacts": {"05_gate_report": "05_gate_report.yaml"},
        },
        {
            "current_stage": "repair_failure",
            "repair_attempts": 1,
            "gate_passed": True,
        },
        {"current_stage": "run_independent_review", "artifacts": {"06_review": "06_review.yaml"}},
        {
            "current_stage": "prepare_evidence",
            "status": RunStatus.CREATED,
            "artifacts": {"07_evidence": "07_evidence.yaml"},
        },
    ]
