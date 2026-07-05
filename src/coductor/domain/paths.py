"""Path-safe identifiers shared by artifact writers and services."""

from __future__ import annotations

import re

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_path_slug(value: str, *, fallback: str = "item") -> str:
    slug = _UNSAFE_CHARS.sub("-", value).strip(".-")
    return slug or fallback
