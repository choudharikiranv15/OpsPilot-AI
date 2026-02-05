"""Tool functions for evidence collection."""

import re
from opspilot.tools.log_tools import analyze_log_errors
from opspilot.tools.env_tools import find_missing_env
from opspilot.tools.dep_tools import has_dependency
from opspilot.tools.pattern_analysis import identify_error_patterns, build_error_timeline


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
    ts_pattern = r'(?:TS-?\d+|error TS\d+)[:\s]+(.+?)(?:\n|$)'
    ts_matches = re.findall(ts_pattern, build_output, re.IGNORECASE)
    if ts_matches:
        errors.extend([{"type": "typescript", "message": m.strip()} for m in ts_matches[:10]])
        error_types.add("typescript")

    # Angular specific errors (X [ERROR])
    angular_pattern = r'X \[ERROR\]\s*([^\n]+(?:\n\s+[^\n]+)*)'
    angular_matches = re.findall(angular_pattern, build_output)
    if angular_matches:
        errors.extend([{"type": "angular", "message": m.strip()} for m in angular_matches[:10]])
        error_types.add("angular")

    # Python errors (SyntaxError, ImportError, etc.)
    py_pattern = r'((?:Syntax|Import|Module|Attribute|Type|Value|Key|Index|Name)Error):\s*(.+?)(?:\n|$)'
    py_matches = re.findall(py_pattern, build_output)
    if py_matches:
        errors.extend([{"type": "python", "error_class": m[0], "message": m[1].strip()} for m in py_matches[:10]])
        error_types.add("python")

    # npm/Node errors
    npm_pattern = r'npm (?:ERR!|error)\s+(.+?)(?:\n|$)'
    npm_matches = re.findall(npm_pattern, build_output, re.IGNORECASE)
    if npm_matches:
        errors.extend([{"type": "npm", "message": m.strip()} for m in npm_matches[:10]])
        error_types.add("npm")

    # Generic error/failed patterns
    generic_pattern = r'(?:error|failed|fatal)[\s:]+(.+?)(?:\n|$)'
    generic_matches = re.findall(generic_pattern, build_output, re.IGNORECASE)
    if generic_matches and not errors:  # Only use if no specific errors found
        errors.extend([{"type": "generic", "message": m.strip()} for m in generic_matches[:10]])
        error_types.add("generic")

    # File references (path:line:col patterns)
    file_refs = re.findall(r'([^\s:]+\.\w+):(\d+)(?::(\d+))?', build_output)
    files_affected = list(set([f[0] for f in file_refs]))[:10]

    return {
        "errors": errors,
        "error_types": list(error_types),
        "files_affected": files_affected,
        "error_count": len(errors),
        "raw_snippet": build_output[:1500] if len(build_output) > 1500 else build_output,
    }


def collect_evidence(context: dict) -> dict:
    """
    Collect evidence from project context with advanced pattern analysis.

    Args:
        context: Project context dictionary

    Returns:
        Dictionary containing collected evidence with error patterns, severity, and timeline
    """
    evidence = {}

    logs = context.get("logs")
    env = context.get("env", {})
    deps = context.get("dependencies", [])
    build_errors = context.get("build_errors")

    # Parse build errors (highest priority)
    if build_errors:
        parsed_build = parse_build_errors(build_errors)
        if parsed_build.get("errors"):
            evidence["build_errors"] = parsed_build
            evidence["severity"] = "P1"  # Build failures are high priority

    # Advanced pattern analysis for logs
    if logs:
        error_patterns = identify_error_patterns(logs)
        if error_patterns:
            evidence["error_patterns"] = error_patterns
            # Don't override severity if build errors already set it
            if "severity" not in evidence:
                evidence["severity"] = error_patterns.get("severity", "P3")
            evidence["error_count"] = error_patterns.get("error_count", 0)

        # Timeline analysis
        timeline = build_error_timeline(logs)
        if timeline:
            evidence["timeline"] = timeline

    # Basic log error counting (keep for backward compatibility)
    log_errors = analyze_log_errors(logs)
    if log_errors:
        evidence["log_errors"] = log_errors

    # Dependency detection
    if has_dependency(deps, "redis"):
        evidence["uses_redis"] = True

    # Environment variable validation (only if no build errors)
    if not build_errors:
        missing_env = find_missing_env(["REDIS_URL"], env)
        if missing_env:
            evidence["missing_env"] = missing_env

    return evidence
