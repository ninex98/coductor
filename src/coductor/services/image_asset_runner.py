"""Image asset request runner with no implicit batch generation."""

from __future__ import annotations

import json
import time
from pathlib import Path

from coductor.config.models import ToolCheckConfig
from coductor.services.tool_execution import ToolExecutionResult


class ImageAssetRunner:
    def __init__(self, root: Path, *, run_dir: Path) -> None:
        self.root = root
        self.run_dir = run_dir

    def run(self, check: ToolCheckConfig) -> ToolExecutionResult:
        start = time.monotonic()
        request_path = self.run_dir / "image_asset_request.json"
        output_path = (self.root / check.image.output_path).resolve()
        parameters = image_parameters(check)
        request_path.write_text(
            json.dumps(parameters, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts = [self._relative(request_path)]
        if _is_inside(output_path, self.root) and output_path.exists() and output_path.is_file():
            artifacts.append(output_path.relative_to(self.root).as_posix())
            return ToolExecutionResult(
                status="passed",
                exit_code=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                stdout="image asset already exists\n",
                stderr="",
                artifacts=artifacts,
                observations={
                    **parameters,
                    "asset_status": "exists",
                    "requires_human": False,
                },
            )
        return ToolExecutionResult(
            status="skipped",
            exit_code=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout="",
            stderr=(
                "image generation backend unavailable; human action required. "
                f"purpose={check.image.purpose or check.description}; "
                f"size={check.image.width}x{check.image.height}; "
                f"candidate_count={check.image.candidate_count}; "
                f"prompt={check.image.prompt or check.description}"
            ),
            artifacts=artifacts,
            observations={
                **parameters,
                "asset_status": "missing",
                "requires_human": True,
                "human_action": "generate_or_provide_image_asset",
            },
        )

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.run_dir.parent.parent).as_posix()


def image_parameters(check: ToolCheckConfig) -> dict[str, object]:
    return {
        "prompt": check.image.prompt or check.description,
        "purpose": check.image.purpose or check.description,
        "output_path": check.image.output_path,
        "width": check.image.width,
        "height": check.image.height,
        "candidate_count": check.image.candidate_count,
        "batch_approved": check.image.batch_approved,
        "reference_paths": check.image.reference_paths,
    }


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    return True
