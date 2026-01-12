"""Remediation plan generator for production incidents."""

from typing import Dict, List


def generate_remediation_plan(hypothesis: str, evidence: Dict, suggestions: List[Dict]) -> Dict:
    """
    Generate manager-friendly remediation plan with immediate, short-term, and long-term actions.

    Args:
        hypothesis: Root cause hypothesis
        evidence: Collected evidence
        suggestions: LLM-generated fix suggestions

    Returns:
        Structured remediation plan with actions, commands, risks, and time estimates
    """
    plan = {
        "immediate_actions": [],
        "short_term_fixes": [],
        "long_term_fixes": [],
        "verification_steps": []
    }

    # Determine issue type from evidence
    severity = evidence.get("severity", "P3")
    uses_redis = evidence.get("uses_redis", False)
    has_timeouts = evidence.get("timeout_errors", 0) > 0
    has_http_5xx = any(
        code.startswith('5')
        for code in evidence.get("error_patterns", {}).get("http_errors", {}).keys()
    )

    # Generate immediate actions based on severity and evidence
    if severity in ["P0", "P1"]:
        if uses_redis and has_timeouts:
            plan["immediate_actions"].extend([
                {
                    "step": 1,
                    "action": "Check Redis service status",
                    "command": "redis-cli ping || systemctl status redis",
                    "risk": "LOW",
                    "estimated_time": "30 seconds",
                    "rationale": "Verify Redis is running and responsive"
                },
                {
                    "step": 2,
                    "action": "Check Redis connection count",
                    "command": "redis-cli info clients | grep connected_clients",
                    "risk": "LOW",
                    "estimated_time": "30 seconds",
                    "rationale": "Identify if connection pool is exhausted"
                },
                {
                    "step": 3,
                    "action": "Restart application service (if safe)",
                    "command": "systemctl restart app-service",
                    "risk": "MEDIUM",
                    "estimated_time": "2 minutes",
                    "rationale": "Clear stale connections and refresh connection pool"
                }
            ])

        if has_http_5xx:
            plan["immediate_actions"].append({
                "step": len(plan["immediate_actions"]) + 1,
                "action": "Check application logs for recent errors",
                "command": "tail -100 /var/log/app/error.log",
                "risk": "LOW",
                "estimated_time": "1 minute",
                "rationale": "Identify immediate cause of 5xx errors"
            })

    # Convert LLM suggestions to short-term fixes
    for idx, suggestion in enumerate(suggestions, 1):
        plan["short_term_fixes"].append({
            "step": idx,
            "action": f"Update {suggestion.get('file', 'configuration')}",
            "file": suggestion.get("file"),
            "diff": suggestion.get("diff"),
            "rationale": suggestion.get("rationale"),
            "risk": "LOW",
            "requires_restart": True
        })

    # Add standard short-term fixes based on evidence
    if uses_redis and has_timeouts:
        plan["short_term_fixes"].extend([
            {
                "step": len(plan["short_term_fixes"]) + 1,
                "action": "Increase Redis timeout",
                "file": ".env or config file",
                "change": "REDIS_TIMEOUT=1 → REDIS_TIMEOUT=5",
                "rationale": "Reduce timeout errors under load",
                "risk": "LOW"
            },
            {
                "step": len(plan["short_term_fixes"]) + 1,
                "action": "Enable Redis connection pooling",
                "file": "app/config/redis.py",
                "change": "Add max_connections=50, socket_timeout=5",
                "rationale": "Prevent connection exhaustion",
                "risk": "LOW"
            }
        ])

    # Generate long-term fixes
    if uses_redis:
        plan["long_term_fixes"].extend([
            {
                "action": "Implement circuit breaker pattern",
                "estimated_effort": "2-3 days",
                "rationale": "Prevent cascading failures when Redis is unavailable"
            },
            {
                "action": "Add Redis connection monitoring",
                "estimated_effort": "1 day",
                "rationale": "Alert on connection pool exhaustion before it causes issues"
            },
            {
                "action": "Implement Redis failover/HA setup",
                "estimated_effort": "1 week",
                "rationale": "Ensure Redis availability with automatic failover"
            }
        ])

    # Generate verification steps
    if severity in ["P0", "P1"]:
        plan["verification_steps"] = [
            "Monitor error rate (should drop to <5/min within 5 minutes)",
            "Check Redis connection count (should stabilize below 80% of max)",
            "Verify application response time (should return to normal)",
            "Check for any new errors in logs"
        ]
    else:
        plan["verification_steps"] = [
            "Monitor error rate over next 24 hours",
            "Review application metrics for improvements",
            "Check logs for recurring patterns"
        ]

    return plan


def format_remediation_output(plan: Dict) -> str:
    """
    Format remediation plan as human-readable text.

    Args:
        plan: Remediation plan dictionary

    Returns:
        Formatted multi-line string
    """
    output = []

    if plan.get("immediate_actions"):
        output.append("\n🔥 IMMEDIATE ACTIONS (0-5 min):")
        output.append("=" * 60)
        for action in plan["immediate_actions"]:
            output.append(f"\n{action['step']}. {action['action']}")
            if action.get("command"):
                output.append(f"   Command: {action['command']}")
            output.append(f"   Risk: {action['risk']} | Time: {action['estimated_time']}")
            if action.get("rationale"):
                output.append(f"   Why: {action['rationale']}")

    if plan.get("short_term_fixes"):
        output.append("\n\n📋 SHORT-TERM FIXES (1-24 hours):")
        output.append("=" * 60)
        for fix in plan["short_term_fixes"]:
            output.append(f"\n{fix['step']}. {fix['action']}")
            if fix.get("file"):
                output.append(f"   File: {fix['file']}")
            if fix.get("change"):
                output.append(f"   Change: {fix['change']}")
            elif fix.get("diff"):
                output.append(f"   Diff: [See above]")
            if fix.get("rationale"):
                output.append(f"   Why: {fix['rationale']}")
            if fix.get("risk"):
                output.append(f"   Risk: {fix['risk']}")

    if plan.get("long_term_fixes"):
        output.append("\n\n🔧 LONG-TERM FIXES (1-4 weeks):")
        output.append("=" * 60)
        for idx, fix in enumerate(plan["long_term_fixes"], 1):
            output.append(f"\n{idx}. {fix['action']}")
            if fix.get("estimated_effort"):
                output.append(f"   Effort: {fix['estimated_effort']}")
            if fix.get("rationale"):
                output.append(f"   Why: {fix['rationale']}")

    if plan.get("verification_steps"):
        output.append("\n\n✅ VERIFICATION STEPS:")
        output.append("=" * 60)
        for idx, step in enumerate(plan["verification_steps"], 1):
            output.append(f"{idx}. {step}")

    return "\n".join(output)
