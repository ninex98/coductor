"""Artifact repository with atomic writes, history, and hash checks."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from coductor.artifacts.models import ArtifactEnvelope, ArtifactInput
from coductor.artifacts.serializer import compute_content_sha256, dump_yaml, load_yaml
from coductor.domain.enums import ArtifactType


class ArtifactRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "history").mkdir(parents=True, exist_ok=True)

    def write(self, relative_path: str, envelope: ArtifactEnvelope[Any]) -> Path:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        envelope.metadata.content_sha256 = compute_content_sha256(envelope)
        text = dump_yaml(envelope.model_dump(mode="json"))
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
        self._write_history(relative_path, target, envelope.revision)
        return target

    def write_next_revision(
        self,
        relative_path: str,
        envelope: ArtifactEnvelope[Any],
    ) -> ArtifactEnvelope[Any]:
        current_path = self.root / relative_path
        if current_path.exists():
            current = self.read(relative_path)
            envelope.revision = current.revision + 1
        else:
            envelope.revision = 1
        self.write(relative_path, envelope)
        return envelope

    def read(
        self,
        path: Path | str,
        artifact_type: ArtifactType | None = None,
    ) -> ArtifactEnvelope[Any]:
        target = path if isinstance(path, Path) else self.root / path
        data = load_yaml(target.read_text(encoding="utf-8"))
        envelope = ArtifactEnvelope[Any].model_validate(data)
        if artifact_type is not None and envelope.artifact_type != artifact_type:
            raise ValueError(
                f"expected artifact_type {artifact_type}, got {envelope.artifact_type}"
            )
        expected = envelope.metadata.content_sha256
        actual = compute_content_sha256(envelope)
        if expected != actual:
            raise ValueError(
                f"artifact hash mismatch for {target}: expected {expected}, got {actual}"
            )
        return envelope

    def input_for(self, relative_path: str, envelope: ArtifactEnvelope[Any]) -> dict[str, Any]:
        return {
            "artifact_type": envelope.artifact_type,
            "path": relative_path,
            "revision": envelope.revision,
            "sha256": envelope.metadata.content_sha256,
        }

    def is_current(self, relative_path: str, inputs: list[ArtifactInput]) -> bool:
        target = self.root / relative_path
        if not target.exists():
            return False
        try:
            artifact = self.read(relative_path)
        except (OSError, ValueError):
            return False
        return artifact.inputs == inputs

    def _write_history(self, relative_path: str, target: Path, revision: int) -> None:
        history_name = relative_path.replace("/", "__").replace(".yaml", f".rev{revision}.yaml")
        history_path = self.root / "history" / history_name
        shutil.copyfile(target, history_path)
