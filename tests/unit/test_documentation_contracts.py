from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backend_docs_match_plain_text_codex_exec_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    docs = readme + "\n" + architecture

    assert "--output-schema" not in docs
    assert "--json" not in docs
    assert "codex exec --sandbox" in docs
    assert "Coductor" in docs
    assert "固定 YAML" in docs


def test_docs_describe_contextual_graph_as_current_orchestrator() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    workflow = (ROOT / "docs" / "workflow.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    adr = (ROOT / "docs" / "adr" / "0003-langgraph-as-orchestrator.md").read_text(
        encoding="utf-8"
    )
    docs = "\n".join([readme, workflow, architecture, adr])

    assert "contextual LangGraph" in docs
    assert "langgraph-checkpoint-sqlite" in docs
    assert "compile_workflow_graph" in docs
    assert "WorkflowGraphRunner 负责当前垂直切片" not in docs
    assert "真实阶段副作用仍由服务层执行" not in docs
    assert "后续会把各阶段副作用继续迁入薄节点" not in docs
