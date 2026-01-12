"""Tool functions for evidence collection."""

from opspilot.tools.log_tools import analyze_log_errors
from opspilot.tools.env_tools import find_missing_env
from opspilot.tools.dep_tools import has_dependency
from opspilot.tools.pattern_analysis import identify_error_patterns, build_error_timeline


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

    # Advanced pattern analysis
    if logs:
        error_patterns = identify_error_patterns(logs)
        if error_patterns:
            evidence["error_patterns"] = error_patterns
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

    # Environment variable validation
    missing_env = find_missing_env(["REDIS_URL"], env)
    if missing_env:
        evidence["missing_env"] = missing_env

    return evidence
