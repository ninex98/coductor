from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import ArtifactEnvelope, GoalData, Producer
from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import ArtifactStatus, ArtifactType, ExecutionMode, ProducerKind
from coductor.storage.database import Database
from coductor.web.app import create_app

CONTROL_TOKEN = "smoke-control-token"


def _headers(*, origin: str = "http://127.0.0.1:8765") -> dict[str, str]:
    return {
        "Host": "127.0.0.1:8765",
        "Origin": origin,
        "X-Coductor-Token": CONTROL_TOKEN,
    }


def _seed_smoke_run(root: Path) -> Path:
    run_id = "run_smoke"
    run_dir = root / ".coductor" / "runs" / run_id
    run_dir.mkdir(parents=True)
    repo = ArtifactRepository(run_dir)
    repo.write(
        "00_goal.yaml",
        ArtifactEnvelope[GoalData](
            artifact_type=ArtifactType.GOAL,
            artifact_id="art_goal_smoke",
            run_id=run_id,
            revision=1,
            status=ArtifactStatus.ACCEPTED,
            created_at="2026-06-24T00:00:00Z",
            producer=Producer(kind=ProducerKind.HUMAN, name="smoke"),
            inputs=[],
            data=GoalData(
                title="Smoke local console",
                raw_request="Smoke local console",
                goal_type="test",
                requested_mode=ExecutionMode.AUTO,
            ),
        ),
    )
    log_dir = run_dir / "logs"
    log_dir.mkdir()
    (log_dir / "unit.stdout.log").write_text(
        "OPENAI_API_KEY=sk-test-secret\nAuthorization: Bearer bearer-secret\n",
        encoding="utf-8",
    )
    db = Database(root / ".coductor" / "coductor.sqlite3")
    db.upsert_run(run_id, "running", run_dir.as_posix(), "2026-06-24T00:00:00Z")
    db.add_event(run_id, "collect_goal", "accepted smoke goal", "2026-06-24T00:00:01Z")
    return run_dir


def test_web_console_smoke_checklist_documents_security_checks() -> None:
    checklist = Path("docs/web-console-smoke-checklist.md")

    text = checklist.read_text(encoding="utf-8")

    assert "coductor serve" in text
    assert "/api/runs" in text
    assert "X-Coductor-Token" in text
    assert "429" in text
    assert "[REDACTED]" in text


def test_web_console_smoke_flow_covers_read_redaction_and_action_guards(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_smoke_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = create_app(tmp_path, control_token=CONTROL_TOKEN)

    index = app.handle("GET", "/")
    health = app.handle("GET", "/api/health")
    runs = app.handle("GET", "/api/runs")
    detail = app.handle("GET", "/api/runs/run_smoke")
    log = app.handle("GET", "/api/runs/run_smoke/logs/logs/unit.stdout.log")
    missing_token = app.handle("POST", "/api/runs/run_smoke/actions/pause")
    wrong_origin = app.handle(
        "POST",
        "/api/runs/run_smoke/actions/pause",
        headers=_headers(origin="http://evil.example"),
    )
    pause = app.handle("POST", "/api/runs/run_smoke/actions/pause", headers=_headers())
    duplicate_pause = app.handle(
        "POST",
        "/api/runs/run_smoke/actions/pause",
        headers=_headers(),
    )

    assert index.status == 200
    assert 'name="coductor-control-token"' in index.text
    assert health.status == 200
    assert runs.body["data"][0]["run_id"] == "run_smoke"
    assert detail.body["data"]["artifacts"][0]["path"] == "00_goal.yaml"
    assert "sk-test-secret" not in log.body["data"]["raw_text"]
    assert "bearer-secret" not in log.body["data"]["raw_text"]
    assert "OPENAI_API_KEY=[REDACTED]" in log.body["data"]["raw_text"]
    assert "Authorization: Bearer [REDACTED]" in log.body["data"]["raw_text"]
    assert missing_token.status == 403
    assert wrong_origin.status == 403
    assert pause.status == 200
    assert duplicate_pause.status == 429
