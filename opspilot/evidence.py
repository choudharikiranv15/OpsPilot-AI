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
# Summary lines that report zero problems ("Failed: 0", "0 errors", "errors=0").
_ZERO_PROBLEMS = re.compile(
    r"(?i)\b(?:fail(?:ed|ures?)?|errors?)\b\W{0,3}[:=]?\s*0\b(?!\.\d)"
    r"|\b0\s+(?:fail(?:ed|ures?)?|errors?)\b"
)


def is_error_line(line: str) -> bool:
    """True for lines that report a problem (excluding 'Failed: 0' summaries)."""
    return bool(_ERROR_LINE.search(line)) and not _ZERO_PROBLEMS.search(line)


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
        builder.add(
            "config", _undefined_env_text(undefined_env), source="source code scan"
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


def _undefined_env_text(undefined_env: dict[str, str]) -> str:
    """Fit as many variable names as possible within the fact length limit."""
    prefix = (
        "Environment variables referenced in code but not defined in the project's "
        ".env files (they may still be set at runtime): "
    )
    items = list(undefined_env.items())
    for with_files in (True, False):
        for count in range(len(items), 0, -1):
            shown = items[:count]
            names = ", ".join(f"{n} ({w})" if with_files else n for n, w in shown)
            more = f" and {len(items) - count} more" if count < len(items) else ""
            text = prefix + names + more
            if len(text) <= MAX_FACT_CHARS and (count == len(items) or not with_files):
                return text
    return prefix + f"{len(items)} variables"


# Compiler-style diagnostics with a location:
#   src/a.ts(12,5): error TS2322: msg          (tsc)
#   src/a.ts:12:5 - error TS2322: msg          (tsc --pretty)
#   app/x.py:12: error: msg  [arg-type]        (mypy)
#   main.go:12:5: undefined: foo / x.c:3:1: error: msg   (go, gcc, clang, eslint unix)
_DIAGNOSTIC_PATTERNS = [
    re.compile(
        r"^(?P<file>[^\s()][^()\n]*?)\((?P<line>\d+),\d+\):\s+(?:error|warning)\s+"
        r"(?P<code>[A-Z]+\d+):\s*(?P<msg>.+)$",
        re.M,
    ),
    re.compile(
        r"^(?P<file>[^\s:]+\.\w+):(?P<line>\d+):\d+\s+-\s+error\s+(?P<code>[A-Z]+\d+):\s*(?P<msg>.+)$",
        re.M,
    ),
    re.compile(
        r"^(?P<file>[^\s:]+\.pyi?):(?P<line>\d+):(?:\d+:)?\s+error:\s+(?P<msg>.+?)"
        r"(?:\s+\[(?P<code>[\w-]+)\])?$",
        re.M,
    ),
    re.compile(
        r"^(?P<file>[^\s:]+\.(?:go|c|cc|cpp|h|hpp|rs|java|kt|swift|js|jsx|ts|tsx|mjs|cjs)):"
        r"(?P<line>\d+):\d+:\s+(?:(?:fatal\s+)?error:\s+)?(?P<msg>.+)$",
        re.M,
    ),
]


def _diagnostics(output: str) -> list[dict]:
    for pattern in _DIAGNOSTIC_PATTERNS:
        found = [m.groupdict() for m in pattern.finditer(output)]
        if found:
            return found
    return []


def _diagnostic_facts(
    builder: FactBuilder, diagnostics: list[dict], source: str, root: Path
) -> None:
    """Group located compiler diagnostics by (code, message), most frequent first."""
    groups: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
    per_file: dict[str, int] = {}
    for d in diagnostics:
        msg = d["msg"].strip()
        groups.setdefault((d.get("code") or "", _VOLATILE.sub("#", msg)), []).append(d)
        per_file[d["file"]] = per_file.get(d["file"], 0) + 1

    codes: dict[str, int] = {}
    for (code, _), items in groups.items():
        if code:
            codes[code] = codes.get(code, 0) + len(items)
    top_codes = ", ".join(
        f"{c} x{n}" for c, n in sorted(codes.items(), key=lambda kv: -kv[1])[:6]
    )
    top_files = ", ".join(
        f"{f} ({n})" for f, n in sorted(per_file.items(), key=lambda kv: -kv[1])[:5]
    )
    if len(diagnostics) > 1:
        builder.add(
            "build_error",
            f"{len(diagnostics)} errors in {len(per_file)} files"
            + (f"; by code: {top_codes}" if top_codes else "")
            + f"; most affected files: {top_files}",
            source=source,
            count=len(diagnostics),
        )

    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    for (code, _), items in ranked[: MAX_BUILD_FACTS - 1]:
        first = items[0]
        files = sorted({d["file"] for d in items})
        rel = project_relative(first["file"], root)
        where = files[0] if len(files) == 1 else f"{len(files)} files, e.g. {files[0]}"
        builder.add(
            "build_error",
            f"{code + ': ' if code else ''}{first['msg'].strip()} "
            f"(in {where}, first at line {first['line']})",
            source=source,
            count=len(items),
            location=f"{rel}:{first['line']}" if rel else None,
        )
    hidden = len(ranked) - (MAX_BUILD_FACTS - 1)
    if hidden > 0:
        builder.add(
            "build_error",
            f"{hidden} further distinct error message(s) not listed",
            source=source,
        )


def _build_facts(builder: FactBuilder, output: str, source: str, root: Path) -> None:
    diagnostics = _diagnostics(output)
    if diagnostics:
        _diagnostic_facts(builder, diagnostics, source, root)
        _frame_facts(builder, output, source, root)
        return
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
        if not is_error_line(raw):
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
        if is_error_line(raw):
            stripped = _TIMESTAMP.sub("", raw).strip()
            if stripped:
                lines.append(stripped)
    return lines
