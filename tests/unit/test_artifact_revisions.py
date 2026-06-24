from __future__ import annotations

from pathlib import Path

from coductor.artifacts.models import (
    AcceptanceCriterion,
    ArtifactEnvelope,
    ArtifactInput,
    GoalData,
    Producer,
    SpecificationData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.artifacts.validator import ArtifactLineageValidator
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ProducerKind,
    VerificationType,
)


def make_goal(title: str) -> ArtifactEnvelope[GoalData]:
    return ArtifactEnvelope[GoalData](
        artifact_type=ArtifactType.GOAL,
        artifact_id=f"art_goal_{title}",
        run_id="run_revision_test",
        revision=1,
        status=ArtifactStatus.ACCEPTED,
        created_at="2026-06-24T00:00:00Z",
        producer=Producer(kind=ProducerKind.HUMAN, name="cli-user"),
        data=GoalData(
            title=title,
            raw_request=title,
            goal_type="feature",
            requested_mode=ExecutionMode.AUTO,
        ),
    )


def make_spec(inputs: list[ArtifactInput]) -> ArtifactEnvelope[SpecificationData]:
    return ArtifactEnvelope[SpecificationData](
        artifact_type=ArtifactType.SPECIFICATION,
        artifact_id="art_spec_revision_test",
        run_id="run_revision_test",
        revision=1,
        status=ArtifactStatus.APPROVED,
        created_at="2026-06-24T00:00:01Z",
        producer=Producer(kind=ProducerKind.MODEL, name="specification-agent"),
        inputs=inputs,
        data=SpecificationData(
            objective="first",
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="AC001",
                    statement="validated",
                    verification=VerificationType.AUTOMATED,
                )
            ],
        ),
    )


def test_write_next_revision_preserves_history(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    first = make_goal("first")
    second = make_goal("second")

    repo.write("00_goal.yaml", first)
    updated = repo.write_next_revision("00_goal.yaml", second)

    assert updated.revision == 2
    assert repo.read("00_goal.yaml").revision == 2
    assert (tmp_path / "history" / "00_goal.rev1.yaml").exists()
    assert (tmp_path / "history" / "00_goal.rev2.yaml").exists()


def test_is_current_compares_recorded_inputs(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    repo.write("00_goal.yaml", make_goal("first"))
    goal = repo.read("00_goal.yaml")
    inputs = [ArtifactInput.model_validate(repo.input_for("00_goal.yaml", goal))]

    repo.write("02_spec.yaml", make_spec(inputs))

    assert repo.is_current("02_spec.yaml", inputs)
    repo.write_next_revision("00_goal.yaml", make_goal("changed"))
    changed_goal = repo.read("00_goal.yaml")
    changed_inputs = [
        ArtifactInput.model_validate(repo.input_for("00_goal.yaml", changed_goal))
    ]
    assert not repo.is_current("02_spec.yaml", changed_inputs)


def test_downstream_artifact_is_stale_when_input_hash_changes(tmp_path: Path) -> None:
    repo = ArtifactRepository(tmp_path)
    repo.write("00_goal.yaml", make_goal("first"))
    goal = repo.read("00_goal.yaml")
    inputs = [ArtifactInput.model_validate(repo.input_for("00_goal.yaml", goal))]
    spec_path = repo.write("02_spec.yaml", make_spec(inputs))

    goal_path = tmp_path / "00_goal.yaml"
    goal_path.write_text(
        goal_path.read_text(encoding="utf-8").replace("first", "changed"),
        encoding="utf-8",
    )

    errors = ArtifactLineageValidator(repo).validate_inputs(spec_path)

    assert any("hash mismatch" in error for error in errors)
