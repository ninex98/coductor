"""Deterministic specification derivation from a raw goal and repository facts."""

from __future__ import annotations

from coductor.artifacts.models import AcceptanceCriterion, RepositorySnapshotData
from coductor.domain.enums import VerificationType


def build_acceptance_criteria(raw_goal: str) -> list[AcceptanceCriterion]:
    normalized = raw_goal.lower()
    criteria = [
        AcceptanceCriterion(
            id="AC001",
            statement="必需质量门通过，且生成 evidence bundle",
            verification=VerificationType.AUTOMATED,
            priority="required",
        )
    ]
    next_id = 2
    for marker, statement in [
        ("cli", "CLI 行为符合目标描述，失败路径给出可恢复的下一步命令"),
        ("review", "review 结果被写入固定 YAML Artifact，并能表达 blocking finding"),
        ("evidence", "evidence bundle 只在质量门、review 和 patch 证据均可信时 ready"),
        ("测试", "新增或更新自动化测试覆盖本次行为变更"),
        ("test", "新增或更新自动化测试覆盖本次行为变更"),
        ("图片", "需要的图片资产已生成或明确进入人工生图，并记录用途、尺寸、prompt 和证据路径"),
        ("图像", "需要的图片资产已生成或明确进入人工生图，并记录用途、尺寸、prompt 和证据路径"),
        ("image", "需要的图片资产已生成或明确进入人工生图，并记录用途、尺寸、prompt 和证据路径"),
        ("asset", "需要的图片资产已生成或明确进入人工生图，并记录用途、尺寸、prompt 和证据路径"),
    ]:
        if marker in normalized:
            criteria.append(
                AcceptanceCriterion(
                    id=f"AC{next_id:03d}",
                    statement=statement,
                    verification=VerificationType.AUTOMATED,
                    priority="required",
                )
            )
            next_id += 1
    return _dedupe_criteria(criteria)


def derive_in_scope(raw_goal: str) -> list[str]:
    scope = ["按目标完成最小可验证变更"]
    normalized = raw_goal.lower()
    if "cli" in normalized:
        scope.append("更新 CLI 或控制面相关行为")
    if "review" in normalized:
        scope.append("更新独立审查 Artifact 生成逻辑")
    if "evidence" in normalized:
        scope.append("更新 Evidence Bundle 完整性判断")
    if "测试" in normalized or "test" in normalized:
        scope.append("补充或运行相关自动化验证")
    if _mentions_image_asset(normalized):
        scope.append("生成或接入目标所需图片资产，并留下可追踪证据")
    return scope


def derive_allowed_paths(raw_goal: str, snapshot: RepositorySnapshotData) -> list[str]:
    del snapshot
    normalized = raw_goal.lower()
    paths = ["src/**", "tests/**"]
    if "文档" in normalized or "doc" in normalized or "readme" in normalized:
        paths.append("docs/**")
        paths.append("README.md")
    if "示例" in normalized or "example" in normalized:
        paths.append("examples/**")
    if _mentions_image_asset(normalized):
        paths.append("assets/**")
        paths.append("public/**")
    return paths


def derive_quality_gates(config_gate_ids: list[str], acceptance_ids: list[str]) -> list[str]:
    del acceptance_ids
    return config_gate_ids


def _dedupe_criteria(criteria: list[AcceptanceCriterion]) -> list[AcceptanceCriterion]:
    seen: set[str] = set()
    deduped: list[AcceptanceCriterion] = []
    for criterion in criteria:
        if criterion.statement in seen:
            continue
        seen.add(criterion.statement)
        deduped.append(criterion)
    return [
        criterion.model_copy(update={"id": f"AC{index:03d}"})
        for index, criterion in enumerate(deduped, start=1)
    ]


def _mentions_image_asset(normalized_goal: str) -> bool:
    return any(
        marker in normalized_goal
        for marker in ["图片", "图像", "生图", "配图", "背景图", "logo", "image", "asset"]
    )
