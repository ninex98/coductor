from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coductor.artifacts.models import ArtifactEnvelope, ToolRequestData, ToolResultData
from coductor.artifacts.repository import ArtifactRepository
from coductor.config.models import CoductorConfig, ImageGenerationConfig, ToolCheckConfig
from coductor.domain.enums import ArtifactType
from coductor.planning.spec_builder import build_acceptance_criteria
from coductor.services.tool_verification_service import (
    ToolCapabilityRegistry,
    ToolVerificationService,
)
from coductor.workflow.artifact_writer import WorkflowArtifactWriter


def test_tool_verification_writes_request_result_and_logs(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.tool_checks = [
        ToolCheckConfig(
            id="browser smoke",
            tool="browser",
            command=f"{sys.executable} -c 'print(\"ok\")'",
            timeout_seconds=30,
        )
    ]
    repo = ArtifactRepository(tmp_path / "run")
    writer = WorkflowArtifactWriter(tmp_path, config)

    results = ToolVerificationService(tmp_path, config, writer).run_checks(repo, "run_abc")

    request = ArtifactEnvelope[ToolRequestData].model_validate(
        repo.read(
            "tool_runs/browser-smoke/tool_request.yaml",
            ArtifactType.TOOL_REQUEST,
        ).model_dump(mode="json")
    )
    result = ArtifactEnvelope[ToolResultData].model_validate(
        repo.read(
            "tool_runs/browser-smoke/tool_result.yaml",
            ArtifactType.TOOL_RESULT,
        ).model_dump(mode="json")
    )

    assert len(results) == 1
    assert request.data.tool == "browser"
    assert result.data.status == "passed"
    assert result.inputs[0].path == "tool_runs/browser-smoke/tool_request.yaml"
    assert (repo.root / result.data.stdout_path).read_text(encoding="utf-8") == "ok\n"


def test_tool_verification_failure_has_fingerprint(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.tool_checks = [
        ToolCheckConfig(
            id="api-smoke",
            tool="api",
            command=f"{sys.executable} -c 'import sys; sys.exit(3)'",
            timeout_seconds=30,
        )
    ]
    repo = ArtifactRepository(tmp_path / "run")
    writer = WorkflowArtifactWriter(tmp_path, config)

    [result] = ToolVerificationService(tmp_path, config, writer).run_checks(
        repo,
        "run_abc",
    )

    assert result.data.status == "failed"
    assert result.data.exit_code == 3
    assert result.data.failure_fingerprint


def test_tool_verification_sanitizes_tool_run_paths(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.tool_checks = [
        ToolCheckConfig(
            id="../browser smoke",
            command=f"{sys.executable} -c 'print(1)'",
            timeout_seconds=30,
        )
    ]
    repo = ArtifactRepository(tmp_path / "run")
    writer = WorkflowArtifactWriter(tmp_path, config)

    ToolVerificationService(tmp_path, config, writer).run_checks(repo, "run_abc")

    assert (repo.root / "tool_runs/browser-smoke/tool_result.yaml").exists()
    assert not (tmp_path / "browser smoke").exists()


def test_tool_verification_respects_capability_registry(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.tool_checks = [
        ToolCheckConfig(id="browser-smoke", tool="browser", command="")
    ]
    repo = ArtifactRepository(tmp_path / "run")
    writer = WorkflowArtifactWriter(tmp_path, config)

    [result] = ToolVerificationService(
        tmp_path,
        config,
        writer,
        registry=ToolCapabilityRegistry(supported_tools={"command"}),
    ).run_checks(repo, "run_abc")

    assert result.data.status == "skipped"
    assert "unsupported tool: browser" in (repo.root / result.data.stderr_path).read_text(
        encoding="utf-8"
    )


def test_image_generation_defaults_to_single_candidate() -> None:
    config = ImageGenerationConfig(prompt="product hero image")

    assert config.candidate_count == 1
    assert config.batch_approved is False


def test_batch_image_generation_requires_approval_flag() -> None:
    with pytest.raises(ValueError, match="batch image requests require"):
        ImageGenerationConfig(prompt="variants", candidate_count=2)

    approved = ImageGenerationConfig(
        prompt="variants",
        candidate_count=2,
        batch_approved=True,
    )

    assert approved.candidate_count == 2


def test_planner_adds_image_needed_criterion() -> None:
    criteria = build_acceptance_criteria("为首页生成一张产品背景图片")

    assert any("图片资产" in criterion.statement for criterion in criteria)


def test_image_generation_without_backend_writes_actionable_result(tmp_path: Path) -> None:
    config = CoductorConfig.default()
    config.tool_checks = [
        ToolCheckConfig(
            id="image-asset",
            tool="image_generation",
            description="首页产品背景图",
            image=ImageGenerationConfig(
                prompt="A clean product hero background",
                purpose="首页首屏背景",
                output_path="assets/generated/hero.png",
                width=1200,
                height=800,
            ),
        )
    ]
    repo = ArtifactRepository(tmp_path / "run")
    writer = WorkflowArtifactWriter(tmp_path, config)

    [result] = ToolVerificationService(tmp_path, config, writer).run_checks(repo, "run_abc")
    request = ArtifactEnvelope[ToolRequestData].model_validate(
        repo.read(
            "tool_runs/image-asset/tool_request.yaml",
            ArtifactType.TOOL_REQUEST,
        ).model_dump(mode="json")
    )

    assert result.data.status == "skipped"
    assert result.data.observations["requires_human"] is True
    assert result.data.observations["width"] == 1200
    assert request.data.parameters["candidate_count"] == 1
    assert request.data.parameters["prompt"] == "A clean product hero background"
    assert "image generation backend unavailable" in (
        repo.root / result.data.stderr_path
    ).read_text(encoding="utf-8")
