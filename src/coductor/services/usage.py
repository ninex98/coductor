"""Run usage metrics normalization and aggregation."""

from __future__ import annotations

from collections.abc import Iterable

from coductor.artifacts.models import WorkerUsage
from coductor.backends.base import BackendUsage


def usage_from_backend(
    backend_usage: BackendUsage,
    *,
    prompt: str,
    summary: str,
    duration_ms: int,
) -> WorkerUsage:
    input_tokens = backend_usage.input_tokens
    output_tokens = backend_usage.output_tokens
    estimated = backend_usage.estimated
    if input_tokens is None:
        input_tokens = estimate_tokens(prompt)
        estimated = True
    if output_tokens is None:
        output_tokens = estimate_tokens(summary)
        estimated = True
    total_tokens = backend_usage.total_tokens
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return WorkerUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        duration_ms=(
            backend_usage.duration_ms
            if backend_usage.duration_ms is not None
            else duration_ms
        ),
        estimated=estimated,
        estimated_cost_usd=backend_usage.estimated_cost_usd,
    )


def combine_usage(usages: Iterable[WorkerUsage]) -> WorkerUsage:
    usage_list = list(usages)
    return WorkerUsage(
        input_tokens=_sum_optional(item.input_tokens for item in usage_list),
        output_tokens=_sum_optional(item.output_tokens for item in usage_list),
        total_tokens=_sum_optional(item.total_tokens for item in usage_list),
        duration_ms=_sum_optional(item.duration_ms for item in usage_list),
        estimated=any(item.estimated for item in usage_list),
        estimated_cost_usd=_sum_optional_float(item.estimated_cost_usd for item in usage_list),
    )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _sum_optional(values: Iterable[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _sum_optional_float(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return round(sum(present), 6)
