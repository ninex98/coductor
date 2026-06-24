"""Validation helpers for artifact lineage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import ArtifactEnvelope, TaskData
from coductor.artifacts.repository import ArtifactRepository
from coductor.domain.enums import ArtifactType


class ArtifactLineageValidator:
    def __init__(self, repo: ArtifactRepository) -> None:
        self.repo = repo

    def validate_inputs(self, artifact_path: Path | str) -> list[str]:
        envelope = self.repo.read(artifact_path)
        errors: list[str] = []
        for input_ref in envelope.inputs:
            try:
                upstream = self.repo.read(input_ref.path)
            except Exception as exc:  # noqa: BLE001 - validation should collect context
                errors.append(f"cannot read input {input_ref.path}: {exc}")
                continue
            if upstream.revision != input_ref.revision:
                errors.append(f"revision mismatch for {input_ref.path}")
            if upstream.metadata.content_sha256 != input_ref.sha256:
                errors.append(f"hash mismatch for {input_ref.path}")
        errors.extend(self._validate_contract_inputs(envelope))
        return errors

    def _validate_contract_inputs(self, envelope: ArtifactEnvelope[Any]) -> list[str]:
        if envelope.artifact_type != ArtifactType.TASK:
            return []
        task = TaskData.model_validate(envelope.data)
        errors: list[str] = []
        for contract in task.contracts:
            path = self.repo.root / contract.path
            if not path.exists():
                errors.append(f"contract missing {contract.path}")
                continue
            actual = file_sha256(path)
            if actual != contract.sha256:
                errors.append(
                    f"contract hash mismatch for {contract.path}: "
                    f"expected {contract.sha256}, got {actual}"
                )
        return errors
