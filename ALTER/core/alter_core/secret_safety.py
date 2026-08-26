from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?s)-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----.*?-----END \1-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^:\s/@]+:)([^@\s/]+)(@)"),
        r"\1[REDACTED]\3",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED_JWT]",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\b(?:bp|bpt|botpress)_[A-Za-z0-9_-]{16,}\b", re.IGNORECASE), "[REDACTED_BOTPRESS_TOKEN]"),
    (
        re.compile(
            r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|auth(?:orization)?|password|passwd|secret|cookie|session[_ -]?token|pat)\s*[:=]\s*([^\s,;]{6,})"
        ),
        r"\1=[REDACTED]",
    ),
)


def redact_secrets(text: str) -> tuple[str, bool]:
    safe = text
    changed = False
    for pattern, replacement in _SECRET_PATTERNS:
        updated = pattern.sub(replacement, safe)
        if updated != safe:
            changed = True
            safe = updated
    return safe, changed


def contains_high_confidence_secret(value: Any) -> bool:
    """Recursively inspect JSON-like values for high-confidence secret formats.

    This intentionally avoids generic entropy heuristics so ordinary hashes, IDs,
    source code and prose are not blocked just because they are long strings.
    """
    if isinstance(value, str):
        _safe, changed = redact_secrets(value)
        return changed
    if isinstance(value, dict):
        return any(contains_high_confidence_secret(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_high_confidence_secret(item) for item in value)
    return False
