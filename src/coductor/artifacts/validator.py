"""Validation helpers for artifact lineage."""

from __future__ import annotations

from pathlib import Path

from coductor.artifacts.repository import ArtifactRepository


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
        return errors
