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
