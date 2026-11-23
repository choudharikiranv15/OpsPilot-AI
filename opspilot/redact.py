"""Best-effort redaction of secrets and personal data before text leaves OpsPilot.

Applied to every prompt sent to an LLM (local or cloud) unless disabled with
``--no-redact`` / ``OPSPILOT_REDACT=false``. This is a safety net, not a
guarantee: unusual secret formats can slip through, which is why cloud
providers require an explicit opt-in.
"""

from __future__ import annotations

import re

MASK = "[REDACTED]"

# (pattern, replacement). Order matters: specific formats before generic ones.
_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), MASK),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"), MASK),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"), MASK),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), MASK),
    (re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"), MASK),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), MASK),
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"), MASK),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        MASK,
    ),
    (re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/=-]{16,}"), rf"\1 {MASK}"),
    # Credentials embedded in URLs: scheme://user:password@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+):[^@\s/]+@"), rf"\1:{MASK}@"),
    # key=value / key: value where the key name suggests a secret
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|"
            r"access[_-]?key|private[_-]?key|credential|auth)[A-Za-z0-9_.-]*)"
            r"([\"']?\s*[:=]\s*)([\"']?)(?!\[REDACTED)([^\s\"',;&]{4,})"
        ),
        rf"\1\2\3{MASK}",
    ),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED EMAIL]",
    ),
]


def redact(text: str) -> tuple[str, int]:
    """Return ``text`` with likely secrets masked, and the number of masks applied."""
    total = 0
    for pattern, replacement in _RULES:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total
