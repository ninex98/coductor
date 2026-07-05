"""Validation helpers for artifact lineage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.models import ArtifactEnvelope, EvidenceBundleData, TaskData, ToolResultData
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
        errors.extend(self._validate_tool_result_files(envelope))
        errors.extend(self._validate_evidence_files(envelope))
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

    def _validate_tool_result_files(self, envelope: ArtifactEnvelope[Any]) -> list[str]:
        if envelope.artifact_type != ArtifactType.TOOL_RESULT:
            return []
        result = ToolResultData.model_validate(envelope.data)
        errors: list[str] = []
        for artifact_path in result.artifacts:
            path = self._safe_repo_path(artifact_path)
            if path is None:
                errors.append(f"tool artifact path escapes run dir: {artifact_path}")
                continue
            if not path.exists() or not path.is_file():
                errors.append(f"tool artifact missing {artifact_path}")
                continue
            expected_hash = result.artifact_hashes.get(artifact_path)
            if expected_hash is not None:
                actual_hash = file_sha256(path)
                if actual_hash != expected_hash:
                    errors.append(
                        f"tool artifact hash mismatch for {artifact_path}: "
                        f"expected {expected_hash}, got {actual_hash}"
                    )
        for evidence_path in result.evidence_paths:
            if evidence_path == "":
                continue
            path = self._safe_repo_path(evidence_path)
            if path is None:
                errors.append(f"tool evidence path escapes run dir: {evidence_path}")
                continue
            if not path.exists():
                errors.append(f"tool evidence missing {evidence_path}")
        return errors

    def _validate_evidence_files(self, envelope: ArtifactEnvelope[Any]) -> list[str]:
        if envelope.artifact_type != ArtifactType.EVIDENCE_BUNDLE:
            return []
        evidence = EvidenceBundleData.model_validate(envelope.data)
        errors: list[str] = []
        for evidence_file in evidence.evidence_files:
            path = self._safe_repo_path(evidence_file.path)
            if path is None:
                errors.append(f"evidence file path escapes run dir: {evidence_file.path}")
                continue
            if not path.exists() or not path.is_file():
                errors.append(f"evidence file missing {evidence_file.path}")
                continue
            actual_hash = file_sha256(path)
            if actual_hash != evidence_file.sha256:
                errors.append(
                    f"evidence file hash mismatch for {evidence_file.path}: "
                    f"expected {evidence_file.sha256}, got {actual_hash}"
                )
        return errors

    def _safe_repo_path(self, relative_path: str) -> Path | None:
        path = (self.repo.root / relative_path).resolve()
        try:
            path.relative_to(self.repo.root.resolve())
        except ValueError:
            return None
        return path
