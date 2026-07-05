"""Stable relative paths for tool verification artifacts."""

from __future__ import annotations

from coductor.domain.paths import safe_path_slug


def tool_run_id_for_check(check_id: str) -> str:
    return safe_path_slug(check_id, fallback="tool-check")


def tool_request_path_for_check(check_id: str) -> str:
    return f"tool_runs/{tool_run_id_for_check(check_id)}/tool_request.yaml"


def tool_result_path_for_check(check_id: str) -> str:
    return f"tool_runs/{tool_run_id_for_check(check_id)}/tool_result.yaml"
