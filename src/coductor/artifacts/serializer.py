"""Stable YAML serialization and content hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from coductor.artifacts.models import ArtifactEnvelope

yaml: ModuleType | None
try:  # pragma: no cover - exercised in dependency-complete environments
    import yaml as yaml_module
except ModuleNotFoundError:  # pragma: no cover - fallback for bundled runtime
    yaml = None
else:
    yaml = yaml_module


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def envelope_to_dict(
    envelope: ArtifactEnvelope[Any],
    *,
    include_hash: bool = True,
) -> dict[str, Any]:
    data = _plain(envelope)
    if not isinstance(data, dict):
        raise TypeError("artifact envelope must serialize to a mapping")
    if not include_hash:
        data.setdefault("metadata", {})["content_sha256"] = ""
    return data


def compute_content_sha256(envelope: ArtifactEnvelope[Any]) -> str:
    data = envelope_to_dict(envelope, include_hash=False)
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_yaml(data: dict[str, Any]) -> str:
    if yaml is not None:
        dumped = yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
        if not isinstance(dumped, str):
            raise TypeError("yaml.safe_dump did not return text")
        return dumped
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def load_yaml(text: str) -> dict[str, Any]:
    loaded = yaml.safe_load(text) if yaml is not None else json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("artifact root must be a mapping")
    return loaded
