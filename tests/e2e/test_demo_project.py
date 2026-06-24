from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from coductor.artifacts.serializer import load_yaml

ROOT = Path(__file__).resolve().parents[2]
CODUCTOR = ROOT / ".venv" / "bin" / "coductor"
PYTHON = ROOT / ".venv" / "bin" / "python"


def _copy_demo_project(tmp_path: Path) -> Path:
    source = ROOT / "examples" / "demo-python-project"
    demo = tmp_path / "demo-python-project"
    shutil.copytree(source, demo)
    return demo


def _run_cli(demo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [CODUCTOR.as_posix(), *args],
        cwd=demo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_demo_project_generates_complete_evidence(tmp_path: Path) -> None:
    demo = _copy_demo_project(tmp_path)
    init = _run_cli(demo, "init")
    assert init.returncode == 0, init.stderr

    run = _run_cli(
        demo,
        "run",
        "修复示例函数并补充测试",
        "--backend",
        "fake",
    )
    assert run.returncode == 0, run.stderr
    assert "状态: ready_for_human_review" in run.stdout
    match = re.search(r"Run ID: (?P<run_id>run_[A-Z0-9]+)", run.stdout)
    assert match is not None
    run_id = match.group("run_id")
    run_dir = demo / ".coductor" / "runs" / run_id

    evidence_path = run_dir / "07_evidence.yaml"
    report_path = run_dir / "delivery-report.md"
    assert evidence_path.exists()
    assert report_path.exists()
    evidence = load_yaml(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "ready_for_human_review"
    assert evidence["data"]["final_status"] == "ready_for_human_review"
    assert evidence["data"]["validation"]["valid"] is True
    assert any(
        item["type"] == "patch"
        for item in evidence["data"]["evidence_files"]
    )
