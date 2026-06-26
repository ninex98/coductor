"""Stage artifact writers for the deterministic workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coductor.artifacts.models import (
    AcceptanceCriterion,
    ArtifactEnvelope,
    ArtifactInput,
    ArtifactMetadata,
    GoalData,
    Producer,
    RepositorySnapshotData,
    SpecificationData,
)
from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig
from coductor.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ExecutionMode,
    ExecutionStrategy,
    ProducerKind,
    VerificationType,
)
from coductor.domain.ids import new_id
from coductor.planning.planner import (
    choose_strategy,
    create_parallel_plan,
    create_pipeline_plan,
    create_solo_plan,
)
from coductor.repository.inspector import RepositoryInspector


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class WorkflowArtifactWriter:
    def __init__(self, root: Path, config: CoductorConfig) -> None:
        self.root = root
        self.config = config

    def envelope(
        self,
        *,
        run_id: str,
        artifact_type: ArtifactType,
        artifact_id_prefix: str,
        status: ArtifactStatus | str,
        producer: Producer,
        data: Any,
        inputs: list[ArtifactInput] | None = None,
    ) -> ArtifactEnvelope[Any]:
        return ArtifactEnvelope[Any](
            artifact_type=artifact_type,
            artifact_id=new_id(artifact_id_prefix),
            run_id=run_id,
            revision=1,
            status=status,
            created_at=utc_now(),
            producer=producer,
            inputs=inputs or [],
            metadata=ArtifactMetadata(),
            data=data,
        )

    def write_goal(
        self,
        repo: ArtifactRepository,
        run_id: str,
        raw_goal: str,
        requested_mode: ExecutionMode,
    ) -> ArtifactEnvelope[GoalData]:
        goal_type = (
            "bugfix"
            if any(word in raw_goal for word in ["修复", "fix", "bug"])
            else "feature"
        )
        data = GoalData(
            title=raw_goal[:60],
            raw_request=raw_goal,
            goal_type=goal_type,
            requested_mode=requested_mode,
            target_repository=".",
            user_constraints=[],
        )
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.GOAL,
            artifact_id_prefix="art_goal",
            status=ArtifactStatus.ACCEPTED,
            producer=Producer(kind=ProducerKind.HUMAN, name="cli-user"),
            data=data,
        )
        repo.write("00_goal.yaml", envelope)
        return envelope

    def write_snapshot(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
    ) -> ArtifactEnvelope[RepositorySnapshotData]:
        data = RepositoryInspector(self.root, self.config).inspect()
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.REPOSITORY_SNAPSHOT,
            artifact_id_prefix="art_repo",
            status=ArtifactStatus.COMPLETE,
            producer=Producer(kind=ProducerKind.SYSTEM, name="repository-inspector"),
            inputs=[ArtifactInput.model_validate(repo.input_for("00_goal.yaml", goal))],
            data=data,
        )
        repo.write("01_repository_snapshot.yaml", envelope)
        return envelope

    def write_spec(
        self,
        repo: ArtifactRepository,
        run_id: str,
        goal: ArtifactEnvelope[GoalData],
        snapshot: ArtifactEnvelope[RepositorySnapshotData],
    ) -> ArtifactEnvelope[SpecificationData]:
        data = SpecificationData(
            objective=goal.data.raw_request,
            in_scope=["按目标完成最小可验证变更", "补充或运行相关验证"],
            out_of_scope=["Web 控制台", "自动 PR", "远程推送", "生产环境操作"],
            constraints=[
                "危险能力默认关闭",
                "完成状态只由质量门和审查证据决定",
            ],
            assumptions=[],
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="AC001",
                    statement="必需质量门通过，且生成 evidence bundle",
                    verification=VerificationType.AUTOMATED,
                    priority="required",
                )
            ],
            risks=snapshot.data.risks,
            unresolved_questions=[],
        )
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.SPECIFICATION,
            artifact_id_prefix="art_spec",
            status=ArtifactStatus.APPROVED,
            producer=Producer(kind=ProducerKind.MODEL, name="specification-agent"),
            inputs=[
                ArtifactInput.model_validate(repo.input_for("00_goal.yaml", goal)),
                ArtifactInput.model_validate(
                    repo.input_for("01_repository_snapshot.yaml", snapshot)
                ),
            ],
            data=data,
        )
        repo.write("02_spec.yaml", envelope)
        return envelope

    def write_plan(
        self,
        repo: ArtifactRepository,
        run_id: str,
        spec: ArtifactEnvelope[SpecificationData],
        snapshot: ArtifactEnvelope[RepositorySnapshotData],
        requested_mode: ExecutionMode,
    ) -> ArtifactEnvelope[Any]:
        decision = choose_strategy(spec.data.objective, requested_mode=requested_mode)
        if decision.strategy == ExecutionStrategy.PIPELINE:
            data = create_pipeline_plan(
                spec.data,
                snapshot.data.base_commit,
                decision.reasoning,
            )
        elif decision.strategy == ExecutionStrategy.PARALLEL:
            data = create_parallel_plan(
                spec.data,
                snapshot.data.base_commit,
                decision.reasoning,
            )
        else:
            data = create_solo_plan(spec.data, snapshot.data.base_commit)
        envelope = self.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.EXECUTION_PLAN,
            artifact_id_prefix="art_plan",
            status=ArtifactStatus.VALIDATED if data.validation.valid else ArtifactStatus.FAILED,
            producer=Producer(kind=ProducerKind.MODEL, name="planning-agent"),
            inputs=[
                ArtifactInput.model_validate(repo.input_for("02_spec.yaml", spec)),
                ArtifactInput.model_validate(
                    repo.input_for("01_repository_snapshot.yaml", snapshot)
                ),
            ],
            data=data,
        )
        repo.write("03_execution_plan.yaml", envelope)
        return envelope
