"""Deterministic evidence: numbered facts extracted from the inputs.

Facts are the only thing the diagnosis may cite. They are produced by plain
parsing (no AI), so every fact can be traced back to a log line, build
output, a source file, or git history.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from opspilot.models import Fact
from opspilot.tools import parse_build_errors
from opspilot.tools.pattern_analysis import identify_error_patterns

MAX_LOG_FACTS = 25
MAX_BUILD_FACTS = 15
MAX_FRAME_FACTS = 10
MAX_FACT_CHARS = 300

_SECTION = re.compile(r"^=== (.+?) ===$")
_TIMESTAMP = re.compile(
    r"^\s*\[?\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\]?\s*"
)
_ERROR_LINE = re.compile(
    r"\b(?:ERROR|FATAL|CRITICAL|SEVERE|PANIC)\b"
    r"|\b[A-Z]\w*(?:Error|Exception)\b"
    r"|Traceback \(most recent call last\)"
    r"|\bpanic:"
    r"|(?i:connection refused|timed out|out of memory|segmentation fault"
    r"|permission denied|no space left|failed)"
)
_FRAME_PATTERNS = [
    re.compile(r'File "([^"]+)", line (\d+)'),  # Python
    re.compile(r"\bat [^\n(]*\(?([^\s():]+\.(?:[cm]?js|tsx?|jsx)):(\d+):\d+\)?"),  # JS
    re.compile(r"\bat [\w.$<>]+\(([\w$]+\.(?:java|kt|scala)):(\d+)\)"),  # JVM
    re.compile(r"^\s*(/?[\w./-]+\.go):(\d+)", re.M),  # Go
    re.compile(r"-->\s*([\w./-]+\.rs):(\d+):\d+"),  # Rust
]
_VOLATILE = re.compile(r"0x[0-9a-fA-F]+|\b\d+\b")


class FactBuilder:
    """Accumulates facts with sequential IDs (F1, F2, ...)."""

    def __init__(self) -> None:
        self.facts: list[Fact] = []

    def add(self, kind: str, text: str, source: str, **extra: Any) -> Fact:
        text = " ".join(text.split())
        if len(text) > MAX_FACT_CHARS:
            text = text[: MAX_FACT_CHARS - 1] + "…"
        fact = Fact(
            id=f"F{len(self.facts) + 1}", kind=kind, text=text, source=source, **extra
        )
        self.facts.append(fact)
        return fact


def build_facts(
    project_root: str,
    *,
    build_output: str | None,
    build_source: str,
    logs: str | None,
    log_source: str | None,
    undefined_env: dict[str, str],
    commits: list[dict] | None,
) -> list[Fact]:
    """Extract numbered facts from all inputs, most important kinds first."""
    builder = FactBuilder()
    root = Path(project_root).resolve()

    if build_output:
        _build_facts(builder, build_output, build_source, root)
    if logs:
        _log_facts(builder, logs, log_source, root)
    if undefined_env:
        shown = list(undefined_env.items())[:10]
        names = ", ".join(f"{name} ({where})" for name, where in shown)
        more = (
            f" and {len(undefined_env) - len(shown)} more"
            if len(undefined_env) > 10
            else ""
        )
        builder.add(
            "config",
            f"Environment variables referenced in code but not defined in the "
            f"project's .env files (they may still be set at runtime): {names}{more}",
            source="source code scan",
        )
    for commit in (commits or [])[:5]:
        files = ", ".join(commit.get("files", [])[:5])
        builder.add(
            "change",
            f"Commit {commit.get('hash')} at {commit.get('date')} by "
            f"{commit.get('author')}: {commit.get('message')}"
            + (f" (files: {files})" if files else ""),
            source="git history",
        )
    return builder.facts


def _build_facts(builder: FactBuilder, output: str, source: str, root: Path) -> None:
    parsed = parse_build_errors(output)
    for error in parsed.get("errors", [])[:MAX_BUILD_FACTS]:
        label = error.get("error_class") or error.get("type", "error")
        builder.add(
            "build_error", f"{label}: {error.get('message', '')}", source=source
        )
    if not parsed.get("errors"):
        for line in _error_lines(output)[-MAX_BUILD_FACTS:]:
            builder.add("build_error", line, source=source)
    _frame_facts(builder, output, source, root)


def _log_facts(builder: FactBuilder, logs: str, source: str | None, root: Path) -> None:
    unique: OrderedDict[str, tuple[str, str, int]] = OrderedDict()
    current = source or "logs"
    for raw in logs.splitlines():
        header = _SECTION.match(raw.strip())
        if header:
            current = header.group(1)
            continue
        if not _ERROR_LINE.search(raw):
            continue
        text = _TIMESTAMP.sub("", raw).strip()
        if not text:
            continue
        key = _VOLATILE.sub("#", text)
        _, _, count = unique.pop(key, ("", "", 0))
        unique[key] = (text, current, count + 1)  # re-insert: most recent last
    for text, where, count in list(unique.values())[-MAX_LOG_FACTS:]:
        builder.add("log_error", text, source=where, count=count)

    patterns = identify_error_patterns(logs)
    summary = _summarize_patterns(patterns)
    if summary:
        builder.add("log_summary", summary, source=source or "logs")
    _frame_facts(builder, logs, source or "logs", root)


def _summarize_patterns(patterns: dict) -> str:
    parts = []
    http = patterns.get("http_errors") or {}
    if http:
        codes = ", ".join(f"{c}×{n}" for c, n in sorted(http.items()))
        parts.append(f"HTTP status codes {codes}")
    if patterns.get("timeout_errors"):
        parts.append(f"{patterns['timeout_errors']} timeout mentions")
    if patterns.get("memory_errors"):
        parts.append(
            "memory exhaustion indicators: " + ", ".join(patterns["memory_errors"])
        )
    if patterns.get("database_errors"):
        parts.append(
            "database/cache errors: " + ", ".join(patterns["database_errors"][:5])
        )
    if patterns.get("stack_traces"):
        parts.append(f"{patterns['stack_traces']} stack trace markers")
    return "Log summary: " + "; ".join(parts) if parts else ""


def _frame_facts(builder: FactBuilder, text: str, source: str, root: Path) -> None:
    seen: set[str] = set()
    added = 0
    for pattern in _FRAME_PATTERNS:
        for path, line in pattern.findall(text):
            rel = project_relative(path, root)
            location = f"{rel or path}:{line}"
            if location in seen:
                continue
            seen.add(location)
            in_project = rel is not None
            builder.add(
                "stack_frame",
                f"Stack frame at {location}"
                + ("" if in_project else " (outside the project or not found)"),
                source=source,
                location=location if in_project else None,
            )
            added += 1
            if added >= MAX_FRAME_FACTS:
                return


def project_relative(path: str, root: Path) -> str | None:
    """Return ``path`` relative to the project if it names an existing project file."""
    candidate = Path(path)
    for base in (candidate, root / candidate):
        try:
            resolved = base.resolve()
        except (OSError, ValueError):
            continue
        if resolved.is_file() and resolved.is_relative_to(root):
            return resolved.relative_to(root).as_posix()
    # Paths from another machine (e.g. /app/src/x.py in a container): match by suffix.
    parts = candidate.parts
    for i in range(1, len(parts)):
        tail = Path(*parts[i:])
        if (root / tail).is_file():
            return tail.as_posix()
    return None


def _error_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        if _ERROR_LINE.search(raw):
            stripped = _TIMESTAMP.sub("", raw).strip()
            if stripped:
                lines.append(stripped)
    return lines
