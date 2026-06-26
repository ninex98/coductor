"""Integration and deterministic quality verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, ArtifactInput, GateReportData, Producer
from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig
from coductor.domain.enums import ArtifactStatus, ArtifactType, ProducerKind
from coductor.gates.models import QualityGate
from coductor.gates.runner import GateRunner
from coductor.repository.merge import build_integration_data
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


class WorkflowVerificationService:
    def __init__(
        self,
        root: Path,
        config: CoductorConfig,
        artifacts: WorkflowArtifactWriter,
    ) -> None:
        self.root = root
        self.config = config
        self.artifacts = artifacts

    def write_integration(
        self,
        repo: ArtifactRepository,
        run_id: str,
        plan: ArtifactEnvelope[Any],
        completed_task_ids: list[str],
    ) -> None:
        data = build_integration_data(plan.data.strategy, completed_task_ids)
        envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.INTEGRATION,
            artifact_id_prefix="art_integration",
            status=(
                ArtifactStatus.SKIPPED
                if data.status == "skipped"
                else ArtifactStatus.COMPLETE
            ),
            producer=Producer(kind=ProducerKind.SYSTEM, name="integration-manager"),
            data=data,
            inputs=[ArtifactInput.model_validate(repo.input_for("03_execution_plan.yaml", plan))],
        )
        repo.write("04_integration.yaml", envelope)

    def run_gates(
        self,
        repo: ArtifactRepository,
        run_id: str,
    ) -> ArtifactEnvelope[GateReportData]:
        gates = [
            QualityGate(
                id=gate.id,
                stage=gate.stage,
                command=gate.command,
                required=gate.required,
                timeout_seconds=gate.timeout_seconds,
            )
            for gate in self.config.quality_gates
        ]
        data = GateRunner(self.root, run_dir=repo.root).run(gates)
        status = ArtifactStatus.PASSED if data.required_gates_passed else ArtifactStatus.FAILED
        envelope = self.artifacts.envelope(
            run_id=run_id,
            artifact_type=ArtifactType.GATE_REPORT,
            artifact_id_prefix="art_gates",
            status=status,
            producer=Producer(kind=ProducerKind.TOOL, name="gate-runner"),
            data=data,
        )
        repo.write("05_gate_report.yaml", envelope)
        return envelope
