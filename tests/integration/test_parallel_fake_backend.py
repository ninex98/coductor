from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from coductor.artifacts.serializer import load_yaml
from coductor.backends.base import WorkerHandle, WorkerRequest, WorkerResult
from coductor.backends.fake import FakeCodingBackend
from coductor.config.models import CoductorConfig, QualityGateConfig
from coductor.domain.enums import ExecutionMode, RunStatus
from coductor.services.run_service import RunService


def _passing_config() -> CoductorConfig:
    config = CoductorConfig.default()
    config.backend.provider = "fake"
    config.quality_gates = [
        QualityGateConfig(
            id="unit_tests",
            stage="final",
            command=f"{sys.executable} -c 'print(1)'",
            required=True,
            timeout_seconds=30,
        )
    ]
    return config


class RecordingFakeBackend(FakeCodingBackend):
    def __init__(self) -> None:
        super().__init__()
        self.builder_workspaces: list[Path] = []

    def continue_worker(self, handle: WorkerHandle, request: WorkerRequest) -> WorkerResult:
        if request.role == "builder":
            self.builder_workspaces.append(Path(request.workspace_path))
        return super().continue_worker(handle, request)


def test_parallel_fake_backend_merges_safe_tasks(tmp_path: Path) -> None:
    result = RunService(
        tmp_path,
        _passing_config(),
        backend=FakeCodingBackend(),
    ).run(
        "并行更新文档和示例",
        mode=ExecutionMode.PARALLEL,
    )

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    run_dir = Path(result.run_dir)
    integration = load_yaml((run_dir / "04_integration.yaml").read_text())
    assert integration["data"]["status"] == "merged"
    assert integration["data"]["merged_tasks"] == ["T001", "T002"]
    assert integration["data"]["conflicts"] == []
    assert (run_dir / "tasks/T001/task.yaml").exists()
    assert (run_dir / "tasks/T002/task.yaml").exists()


def test_parallel_git_repo_records_worktree_diffs(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "coductor@example.test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Coductor Test"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True)

    result = RunService(
        tmp_path,
        _passing_config(),
        backend=FakeCodingBackend(),
    ).run(
        "并行更新文档和示例",
        mode=ExecutionMode.PARALLEL,
    )

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    run_dir = Path(result.run_dir)
    integration = load_yaml((run_dir / "04_integration.yaml").read_text())
    assert integration["data"]["status"] == "merged"
    assert integration["data"]["worktree_diffs"]
    assert integration["data"]["worktree_diffs"][0]["path"].endswith(".diff")


def test_parallel_git_repo_runs_builders_in_isolated_worktrees(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "coductor@example.test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Coductor Test"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True)
    backend = RecordingFakeBackend()

    result = RunService(
        tmp_path,
        _passing_config(),
        backend=backend,
    ).run(
        "并行更新文档和示例",
        mode=ExecutionMode.PARALLEL,
    )

    assert result.status == RunStatus.READY_FOR_HUMAN_REVIEW
    expected_root = tmp_path / ".coductor" / "worktrees" / result.run_id
    assert len(backend.builder_workspaces) == 2
    assert all(workspace.parent == expected_root for workspace in backend.builder_workspaces)
    assert {workspace.name for workspace in backend.builder_workspaces} == {"T001", "T002"}
    assert all(not workspace.exists() for workspace in backend.builder_workspaces)
    run_dir = Path(result.run_dir)
    request = load_yaml((run_dir / "tasks/T001/worker_request.yaml").read_text())
    assert request["data"]["workspace_path"].endswith(f".coductor/worktrees/{result.run_id}/T001")
