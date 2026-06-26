"""Repository for contract files and contract metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from coductor.artifacts.hashing import file_sha256
from coductor.artifacts.serializer import dump_yaml, load_yaml
from coductor.contracts.models import ContractArtifact

ContractKind = Literal["json_schema", "openapi", "event_schema", "type_definition"]


class ContractRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def record(
        self,
        relative_path: str,
        *,
        kind: ContractKind,
        producer_task_id: str,
    ) -> ContractArtifact:
        path = self.root / relative_path
        contract = ContractArtifact(
            path=relative_path,
            kind=kind,
            sha256=file_sha256(path),
            producer_task_id=producer_task_id,
        )
        self._write_manifest([contract])
        return contract

    def load_manifest(self) -> list[ContractArtifact]:
        manifest = self.root / "contracts" / "contracts.yml"
        if not manifest.exists():
            return []
        data = load_yaml(manifest.read_text(encoding="utf-8"))
        contracts = data.get("contracts", [])
        if not isinstance(contracts, list):
            return []
        return [ContractArtifact.model_validate(item) for item in contracts]

    def _write_manifest(self, contracts: list[ContractArtifact]) -> Path:
        manifest = self.root / "contracts" / "contracts.yml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            dump_yaml({"contracts": [item.model_dump(mode="json") for item in contracts]}),
            encoding="utf-8",
        )
        return manifest
