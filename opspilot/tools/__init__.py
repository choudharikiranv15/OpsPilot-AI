"""Tool functions for evidence collection."""

from opspilot.tools.log_tools import analyze_log_errors
from opspilot.tools.env_tools import find_missing_env
from opspilot.tools.dep_tools import has_dependency


def collect_evidence(context: dict) -> dict:
    """
    Collect evidence from project context.

    Args:
        context: Project context dictionary

    Returns:
        Dictionary containing collected evidence
    """
    evidence = {}

    logs = context.get("logs")
    env = context.get("env", {})
    deps = context.get("dependencies", [])

    log_errors = analyze_log_errors(logs)
    if log_errors:
        evidence["log_errors"] = log_errors

    if has_dependency(deps, "redis"):
        evidence["uses_redis"] = True

    missing_env = find_missing_env(["REDIS_URL"], env)
    if missing_env:
        evidence["missing_env"] = missing_env

    return evidence
