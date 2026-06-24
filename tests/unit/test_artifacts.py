from __future__ import annotations

from pathlib import Path

import pytest

from coductor.artifacts.models import ArtifactEnvelope, GoalData, Producer
from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.serializer import compute_content_sha256
from coductor.domain.enums import ArtifactStatus, ArtifactType, ExecutionMode, ProducerKind


def test_artifact_round_trip_records_hash_and_history(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    artifact = ArtifactEnvelope[GoalData](
        artifact_type=ArtifactType.GOAL,
        artifact_id="art_goal_00000000000000000000000001",
        run_id="run_00000000000000000000000001",
        revision=1,
        status=ArtifactStatus.ACCEPTED,
        created_at="2026-06-24T00:00:00Z",
        producer=Producer(kind=ProducerKind.HUMAN, name="cli-user"),
        inputs=[],
        data=GoalData(
            title="修复示例函数并补充测试",
            raw_request="修复示例函数并补充测试",
            goal_type="bugfix",
            requested_mode=ExecutionMode.AUTO,
            target_repository=".",
            user_constraints=[],
        ),
    )

    path = repo.write("00_goal.yaml", artifact)
    loaded = repo.read(path, ArtifactType.GOAL)

    assert loaded.metadata.content_sha256 == compute_content_sha256(loaded)
    assert loaded.data["title"] == "修复示例函数并补充测试"
    assert (tmp_path / "history" / "00_goal.rev1.yaml").exists()


def test_tampered_artifact_is_rejected(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    artifact = ArtifactEnvelope[GoalData](
        artifact_type=ArtifactType.GOAL,
        artifact_id="art_goal_00000000000000000000000002",
        run_id="run_00000000000000000000000002",
        revision=1,
        status=ArtifactStatus.ACCEPTED,
        created_at="2026-06-24T00:00:00Z",
        producer=Producer(kind=ProducerKind.HUMAN, name="cli-user"),
        inputs=[],
        data=GoalData(
            title="原始目标",
            raw_request="原始目标",
            goal_type="feature",
            requested_mode=ExecutionMode.AUTO,
            target_repository=".",
            user_constraints=[],
        ),
    )

    path = repo.write("00_goal.yaml", artifact)
    path.write_text(
        path.read_text(encoding="utf-8").replace("原始目标", "被篡改"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        repo.read(path, ArtifactType.GOAL)
