"""Small sortable ID helpers.

The MVP uses timestamp-plus-random IDs with ULID-like lexical ordering. They are
prefixed per domain object and stay stable once written to disk.
"""

from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _base32(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        value, remainder = divmod(value, 32)
        chars.append(_ALPHABET[remainder])
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    timestamp_ms = int(time.time() * 1000)
    random_value = secrets.randbits(80)
    return f"{prefix}_{_base32(timestamp_ms, 10)}{_base32(random_value, 16)}"
