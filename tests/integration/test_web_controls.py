from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import (
    ArtifactEnvelope,
    EvidenceBundleData,
    GateSummary,
    GoalData,
    Producer,
    PullRequestInfo,
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
from coductor.services.evidence_service import EvidenceCompletenessValidator
from coductor.storage.database import Database
from coductor.web.app import LocalConsoleApp, create_app

CONTROL_TOKEN = "test-control-token"


def _app(root: Path) -> LocalConsoleApp:
    return create_app(root, control_token=CONTROL_TOKEN)


def _action_headers(*, origin: str = "http://127.0.0.1:8765") -> dict[str, str]:
    return {
        "Host": "127.0.0.1:8765",
        "Origin": origin,
        "X-Coductor-Token": CONTROL_TOKEN,
    }


def _seed_basic_run(root: Path, *, status: str = "running", run_id: str = "run_abc") -> Path:
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
    db.upsert_run(run_id, status, run_dir.as_posix(), "2026-06-24T00:00:00Z")
    db.add_event(run_id, "collect_goal", "accepted user goal", "2026-06-24T00:00:01Z")
    return run_dir


def _seed_ready_release_run(root: Path) -> Path:
    run_dir = _seed_basic_run(root, status="ready_for_human_review")
    repo = ArtifactRepository(run_dir)
    evidence = EvidenceBundleData(
        goal_title="修复示例函数",
        final_status="ready_for_human_review",
        strategy_used=ExecutionStrategy.SOLO,
        base_commit="base",
        head_commit="head",
        completed_tasks=["T001"],
        gate_summary=GateSummary(required=0, passed=0, failed=0),
        review_summary=ReviewSummary(blocking_findings=0),
        evidence_files=[],
        rollback=Rollback(method="git revert", instructions="人工确认后回滚。"),
        pull_request=PullRequestInfo(created=False, title="修复示例函数"),
    )
    evidence.validation = EvidenceCompletenessValidator().validate(evidence)
    evidence.validation.valid = True
    envelope = ArtifactEnvelope[EvidenceBundleData](
        artifact_type=ArtifactType.EVIDENCE_BUNDLE,
        artifact_id="art_evidence_000000000000000000001",
        run_id="run_abc",
        revision=1,
        status=ArtifactStatus.READY_FOR_HUMAN_REVIEW,
        created_at="2026-06-24T00:00:00Z",
        producer=Producer(kind=ProducerKind.SYSTEM, name="evidence-service"),
        inputs=[],
        data=evidence,
    )
    repo.write("07_evidence.yaml", envelope)
    (root / "coductor.yaml").write_text(
        "\n".join(['schema_version: "1.0"', "backend:", "  provider: fake"]) + "\n",
        encoding="utf-8",
    )
    return run_dir


def test_web_action_pause_updates_status(tmp_path: Path, monkeypatch) -> None:
    _seed_basic_run(tmp_path, status="running")
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)

    response = app.handle("POST", "/api/runs/run_abc/actions/pause", headers=_action_headers())

    assert response.status == 200
    assert response.body["data"]["status"] == "paused"
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    assert db.get_run("run_abc")["status"] == "paused"


def test_web_action_release_writes_manifest(tmp_path: Path, monkeypatch) -> None:
    run_dir = _seed_ready_release_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)

    response = app.handle("POST", "/api/runs/run_abc/actions/release", headers=_action_headers())

    assert response.status == 200
    assert response.body["data"]["status"] == "ready_for_human_review"
    assert (run_dir / "08_release_manifest.yaml").exists()


def test_web_action_rejects_duplicate_action_within_short_window(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_ready_release_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)

    first = app.handle("POST", "/api/runs/run_abc/actions/release", headers=_action_headers())
    second = app.handle("POST", "/api/runs/run_abc/actions/release", headers=_action_headers())

    assert first.status == 200
    assert second.status == 429
    assert "too many" in second.body["error"]["message"].lower()


def test_web_action_rate_limit_is_scoped_to_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_basic_run(tmp_path, status="running")
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)

    first = app.handle("POST", "/api/runs/run_abc/actions/pause", headers=_action_headers())
    second = app.handle("POST", "/api/runs/run_abc/actions/stop", headers=_action_headers())

    assert first.status == 200
    assert second.status != 429


def test_web_action_allows_repeat_after_rate_limit_window(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_ready_release_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)
    app.control_service.DEFAULT_ACTION_WINDOW_SECONDS = -1

    first = app.handle("POST", "/api/runs/run_abc/actions/release", headers=_action_headers())
    second = app.handle("POST", "/api/runs/run_abc/actions/release", headers=_action_headers())

    assert first.status == 200
    assert second.status == 200


def test_web_action_rejects_locked_run_without_side_effects(tmp_path: Path, monkeypatch) -> None:
    run_dir = _seed_basic_run(tmp_path, status="running")
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    assert db.acquire_run_lock("run_abc", "other-owner")
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)

    response = app.handle("POST", "/api/runs/run_abc/actions/pause", headers=_action_headers())

    assert response.status == 409
    assert "already locked" in response.body["error"]["message"]
    assert db.get_run("run_abc")["status"] == "running"
    assert not (run_dir / "08_release_manifest.yaml").exists()


def test_web_action_rejects_missing_control_token(tmp_path: Path, monkeypatch) -> None:
    _seed_basic_run(tmp_path, status="running")
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)

    response = app.handle("POST", "/api/runs/run_abc/actions/pause")

    assert response.status == 403
    assert "control token" in response.body["error"]["message"]
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    assert db.get_run("run_abc")["status"] == "running"


def test_web_action_rejects_cross_origin_even_with_control_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_basic_run(tmp_path, status="running")
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)

    response = app.handle(
        "POST",
        "/api/runs/run_abc/actions/pause",
        headers=_action_headers(origin="http://evil.example"),
    )

    assert response.status == 403
    assert "origin" in response.body["error"]["message"].lower()
    db = Database(tmp_path / ".coductor" / "coductor.sqlite3")
    assert db.get_run("run_abc")["status"] == "running"
