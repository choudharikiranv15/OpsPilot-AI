"""Tool functions for evidence collection."""

import re

from opspilot.tools.pattern_analysis import (
    build_error_timeline,
    identify_error_patterns,
)


def parse_build_errors(build_output: str) -> dict:
    """
    Parse build/compilation errors from various build tools.

    Supports: Angular/TypeScript, npm/Node, Python, Go, Rust, Java/Maven/Gradle
    """
    if not build_output:
        return {}

    errors = []
    error_types = set()

    # TypeScript/Angular errors (TS-XXXXXX or TSxxxx)
    ts_pattern = r"(?:TS-?\d+|error TS\d+)[:\s]+(.+?)(?:\n|$)"
    ts_matches = re.findall(ts_pattern, build_output, re.IGNORECASE)
    if ts_matches:
        errors.extend(
            [{"type": "typescript", "message": m.strip()} for m in ts_matches[:10]]
        )
        error_types.add("typescript")

    # Angular specific errors (X [ERROR])
    angular_pattern = r"X \[ERROR\]\s*([^\n]+(?:\n\s+[^\n]+)*)"
    angular_matches = re.findall(angular_pattern, build_output)
    if angular_matches:
        errors.extend(
            [{"type": "angular", "message": m.strip()} for m in angular_matches[:10]]
        )
        error_types.add("angular")

    # Python errors (SyntaxError, ImportError, etc.)
    py_pattern = r"((?:Syntax|Import|Module|Attribute|Type|Value|Key|Index|Name)Error):\s*(.+?)(?:\n|$)"
    py_matches = re.findall(py_pattern, build_output)
    if py_matches:
        errors.extend(
            [
                {"type": "python", "error_class": m[0], "message": m[1].strip()}
                for m in py_matches[:10]
            ]
        )
        error_types.add("python")

    # npm/Node errors
    npm_pattern = r"npm (?:ERR!|error)\s+(.+?)(?:\n|$)"
    npm_matches = re.findall(npm_pattern, build_output, re.IGNORECASE)
    if npm_matches:
        errors.extend([{"type": "npm", "message": m.strip()} for m in npm_matches[:10]])
        error_types.add("npm")

    # Generic error/failed patterns
    generic_pattern = r"(?:error|failed|fatal)[\s:]+(.+?)(?:\n|$)"
    generic_matches = re.findall(generic_pattern, build_output, re.IGNORECASE)
    if generic_matches and not errors:  # Only use if no specific errors found
        errors.extend(
            [{"type": "generic", "message": m.strip()} for m in generic_matches[:10]]
        )
        error_types.add("generic")

    # File references (path:line:col patterns)
    file_refs = re.findall(r"([^\s:]+\.\w+):(\d+)(?::(\d+))?", build_output)
    files_affected = list({f[0] for f in file_refs})[:10]

    return {
        "errors": errors,
        "error_types": list(error_types),
        "files_affected": files_affected,
        "error_count": len(errors),
        "raw_snippet": build_output[:1500]
        if len(build_output) > 1500
        else build_output,
    }


def collect_evidence(context: dict) -> dict:
    """
    Heuristic error statistics for the build output and logs in ``context``.

    Used for the severity estimate and the "seen before" fingerprint. The
    diagnosis itself is based on numbered facts (see opspilot.evidence).
    """
    evidence: dict = {}
    logs = context.get("logs")
    build_output = context.get("build_errors")

    if build_output:
        parsed_build = parse_build_errors(build_output)
        if parsed_build.get("errors"):
            evidence["build_errors"] = parsed_build
            evidence["severity"] = "P1"  # a failing build blocks delivery

    if logs:
        error_patterns = identify_error_patterns(logs)
        if error_patterns:
            evidence["error_patterns"] = error_patterns
            evidence.setdefault("severity", error_patterns.get("severity", "P3"))
            evidence["error_count"] = error_patterns.get("error_count", 0)
        timeline = build_error_timeline(logs)
        if timeline:
            evidence["timeline"] = timeline

    return evidence
