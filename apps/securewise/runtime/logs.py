"""Secret redaction helpers for runtime container logs."""

from __future__ import annotations

import re

# Patterns for common secret shapes that might leak into container stdout/stderr
# (API keys, bearer tokens, connection strings with embedded credentials, etc).
# This is best-effort defense-in-depth — it does not replace not printing
# secrets in the first place.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^\s\"']+)"),
    re.compile(r"(?i)(secret\s*[:=]\s*)([^\s\"']+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)([^\s\"']+)"),
    re.compile(r"(?i)(password\s*[:=]\s*)([^\s\"']+)"),
    re.compile(r"(Bearer\s+)([A-Za-z0-9._-]+)"),
    re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:\s]+:)([^@\s]+)(@)"),  # user:pass@host in URLs
]

_REDACTED = "***REDACTED***"


def redact_secrets(text: str) -> str:
    """Best-effort masking of secret-shaped substrings inside log output."""
    if not text:
        return text
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: m.group(1) + _REDACTED + (m.group(3) if m.lastindex and m.lastindex >= 3 else ""), redacted)
    return redacted


def tail_lines(text: str, max_lines: int = 200) -> str:
    """Keep only the last `max_lines` lines — container logs can be huge."""
    if not text:
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])
