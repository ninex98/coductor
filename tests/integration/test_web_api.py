from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import (
    ArtifactEnvelope,
    EvidenceBundleData,
    GateSummary,
    GoalData,
    Producer,
    ReleaseGitState,
    ReleaseManifestData,
    ReleaseSafety,
    ReviewSummary,
    Rollback,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ExecutionStrategy,
    ProducerKind,
)
from coductor.storage.database import Database
from coductor.web import doctor_service
from coductor.web.app import create_app
from coductor.workflow.checkpoint import WorkflowCheckpointStore
from coductor.workflow.state import WorkflowState


def _seed_run(root: Path, run_id: str = "run_abc") -> Path:
    run_dir = root / ".coductor" / "runs" / run_id
    run_dir.mkdir(parents=True)
    repo = ArtifactRepository(run_dir)
    goal = ArtifactEnvelope[GoalData](
        artifact_type=ArtifactType.GOAL,
        artifact_id="art_goal_00000000000000000000000001",
        run_id=run_id,
        revision=1,
        status=ArtifactStatus.ACCEPTED,
        created_at="2026-06-24T00:00:00Z",
        producer=Producer(kind=ProducerKind.HUMAN, name="cli-user"),
        inputs=[],
        data=GoalData(
            title="修复示例函数",
            raw_request="修复示例函数",
            goal_type="bugfix",
            requested_mode=ExecutionMode.AUTO,
        ),
    )
    repo.write("00_goal.yaml", goal)
    db = Database(root / ".coductor" / "coductor.sqlite3")
    db.upsert_run(run_id, "running", run_dir.as_posix(), "2026-06-24T00:00:00Z")
    db.add_event(run_id, "collect_goal", "accepted user goal", "2026-06-24T00:00:01Z")
    WorkflowCheckpointStore(db, root / ".coductor" / "runs").save(
        WorkflowState(
            run_id=run_id,
            status="running",
            current_stage="dispatch_tasks",
            run_dir=run_dir.as_posix(),
        ),
        "2026-06-24T00:00:02Z",
    )
    return run_dir


def test_local_console_api_health_and_runs(tmp_path: Path) -> None:
    _seed_run(tmp_path)
    app = create_app(tmp_path)

    health = app.handle("GET", "/api/health")
    runs = app.handle("GET", "/api/runs")
    run = app.handle("GET", "/api/runs/run_abc")

    assert health.status == 200
    assert health.body["ok"] is True
    assert health.body["data"]["root"] == tmp_path.as_posix()
    assert runs.body["data"][0]["run_id"] == "run_abc"
    assert run.body["data"]["checkpoint"]["current_stage"] == "dispatch_tasks"
    assert run.body["data"]["artifacts"][0]["path"] == "00_goal.yaml"


def test_local_console_run_list_flags_run_dir_outside_project_runs(tmp_path: Path) -> None:
    outside = tmp_path / "outside-run"
    outside.mkdir()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    db.upsert_run("run_abc", "running", outside.as_posix(), "2026-06-24T00:00:00Z")
    app = create_app(tmp_path)

    response = app.handle("GET", "/api/runs")

    assert response.status == 200
    run = response.body["data"][0]
    assert run["run_id"] == "run_abc"
    assert run["run_dir_valid"] is False
    assert "outside project runs directory" in run["run_dir_error"]


def test_local_console_run_detail_includes_evidence_and_release_summary(
    tmp_path: Path,
) -> None:
    run_dir = _seed_run(tmp_path)
    repo = ArtifactRepository(run_dir)
    evidence = ArtifactEnvelope[EvidenceBundleData](
        artifact_type=ArtifactType.EVIDENCE_BUNDLE,
        artifact_id="art_evidence_00000000000000000001",
        run_id="run_abc",
        revision=1,
        status=ArtifactStatus.READY_FOR_HUMAN_REVIEW,
        created_at="2026-06-24T00:00:03Z",
        producer=Producer(kind=ProducerKind.SYSTEM, name="delivery-manager"),
        data=EvidenceBundleData(
            goal_title="修复示例函数",
            final_status="ready_for_human_review",
            strategy_used=ExecutionStrategy.SOLO,
            base_commit="base",
            head_commit="head",
            completed_tasks=["T001"],
            gate_summary=GateSummary(required=1, passed=1, failed=0),
            review_summary=ReviewSummary(blocking_findings=0),
            rollback=Rollback(method="git revert", instructions="人工回滚。"),
        ),
    )
    repo.write("07_evidence.yaml", evidence)
    release = ArtifactEnvelope[ReleaseManifestData](
        artifact_type=ArtifactType.RELEASE_MANIFEST,
        artifact_id="art_release_00000000000000000001",
        run_id="run_abc",
        revision=1,
        status=ArtifactStatus.READY,
        created_at="2026-06-24T00:00:04Z",
        producer=Producer(kind=ProducerKind.SYSTEM, name="release-service"),
        data=ReleaseManifestData(
            release_id="rel_abc",
            title="修复示例函数",
            status="ready",
            git=ReleaseGitState(
                base_commit="base",
                head_commit="head",
                dirty_worktree=False,
            ),
            safety=ReleaseSafety(ready=True),
            local_commands=["coductor report run_abc"],
            manual_commands=["git status --short"],
        ),
    )
    repo.write("08_release_manifest.yaml", release)
    app = create_app(tmp_path)

    response = app.handle("GET", "/api/runs/run_abc")

    assert response.status == 200
    data = response.body["data"]
    assert data["evidence"]["final_status"] == "ready_for_human_review"
    assert data["evidence"]["gate_summary"]["passed"] == 1
    assert data["release"]["status"] == "ready"
    assert data["release"]["remote_actions_allowed"] is False


def test_local_console_api_reads_artifact_and_rejects_path_escape(tmp_path: Path) -> None:
    _seed_run(tmp_path)
    app = create_app(tmp_path)

    artifact = app.handle("GET", "/api/runs/run_abc/artifacts/00_goal.yaml")
    escaped = app.handle("GET", "/api/runs/run_abc/artifacts/..%2Fcoductor.yaml")

    assert artifact.status == 200
    assert artifact.body["data"]["artifact_type"] == "goal"
    assert artifact.body["data"]["parsed_yaml"]["data"]["title"] == "修复示例函数"
    assert escaped.status == 400
    assert escaped.body["ok"] is False
    assert "traversal" in escaped.body["error"]["message"]


def test_local_console_rejects_run_dir_outside_project_runs(tmp_path: Path) -> None:
    outside = tmp_path / "outside-run"
    outside.mkdir()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    db.upsert_run("run_abc", "running", outside.as_posix(), "2026-06-24T00:00:00Z")
    app = create_app(tmp_path)

    response = app.handle("GET", "/api/runs/run_abc")

    assert response.status == 400
    assert "outside project runs directory" in response.body["error"]["message"]


def test_local_console_serves_static_assets(tmp_path: Path) -> None:
    app = create_app(tmp_path, control_token="console-token")

    index = app.handle("GET", "/")
    css = app.handle("GET", "/static/styles.css")
    js = app.handle("GET", "/static/app.js")

    assert index.status == 200
    assert 'id="app"' in index.text
    assert 'name="coductor-control-token"' in index.text
    assert 'content="console-token"' in index.text
    assert 'data-tab="logs"' in index.text
    assert 'data-tab="evidence"' in index.text
    assert 'data-tab="release"' in index.text
    assert css.status == 200
    assert "coductor-shell" in css.text
    assert js.status == 200
    assert "fetchJson" in js.text
    assert "renderLogs" in js.text
    assert "renderEvidence" in js.text
    assert "renderRelease" in js.text


def test_local_console_doctor_reports_backend_and_permissions(tmp_path: Path) -> None:
    (tmp_path / "coductor.yaml").write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "backend:",
                "  provider: fake",
                "permissions:",
                "  network_access: false",
                "  allow_git_commit: false",
                "  allow_git_push: false",
                "  allow_pull_request: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    app = create_app(tmp_path)

    response = app.handle("GET", "/api/doctor")

    assert response.status == 200
    checks = response.body["data"]["checks"]
    assert checks["backend_provider"] == "fake"
    assert checks["backend_available"] is True
    assert checks["permission_defaults"]["allow_git_push"] is False


def test_local_console_doctor_reports_effective_backend_for_sdk_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "coductor.yaml").write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "backend:",
                "  provider: codex_sdk",
                "  fallback: codex_exec",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor_service, "is_codex_sdk_available", lambda: False)
    app = create_app(tmp_path)

    response = app.handle("GET", "/api/doctor")

    assert response.status == 200
    checks = response.body["data"]["checks"]
    assert checks["backend_provider"] == "codex_sdk"
    assert checks["backend_effective_provider"] == "codex_exec"
    assert checks["backend_available"] is True
