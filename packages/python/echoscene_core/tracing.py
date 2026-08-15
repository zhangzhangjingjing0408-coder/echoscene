"""Trace redaction that runs before persistence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "email",
    "livekit_api_secret",
    "password",
    "phone",
    "secret",
    "token",
}

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or any(
        part in normalized for part in ("api_key", "secret", "password", "authorization")
    )


def _redact_string(value: str) -> str:
    value = BEARER_PATTERN.sub("[REDACTED_AUTH]", value)
    value = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    return PHONE_PATTERN.sub("[REDACTED_PHONE]", value)


def redact_trace(value: Any) -> Any:
    """Return a recursively redacted copy of trace-safe JSON-like data."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else redact_trace(item)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_trace(item) for item in value]
    return value

