"""Unit tests for remediation plan generation."""

import pytest
from opspilot.agents.remediation import (
    generate_remediation_plan,
    format_remediation_output
)


class TestRemediationPlanGeneration:
    """Test remediation plan generation logic."""

    def test_p0_severity_immediate_actions(self):
        """Test P0 severity generates immediate actions."""
        evidence = {
            "severity": "P0",
            "uses_redis": True,
            "timeout_errors": 5,
            "error_patterns": {
                "http_errors": {"500": 12}
            }
        }

        plan = generate_remediation_plan("Redis timeout", evidence, [])

        # P0 should have immediate actions
        assert len(plan["immediate_actions"]) > 0

        # Check for Redis-specific actions
        assert any("Redis" in action["action"] for action in plan["immediate_actions"])

    def test_p3_severity_no_immediate_actions(self):
        """Test P3 severity skips immediate actions."""
        evidence = {
            "severity": "P3",
            "uses_redis": False,
            "timeout_errors": 0,
            "error_patterns": {
                "http_errors": {"404": 5}
            }
        }

        plan = generate_remediation_plan("Client errors", evidence, [])

        # P3 should not have immediate actions
        assert len(plan["immediate_actions"]) == 0

    def test_redis_timeout_short_term_fixes(self):
        """Test Redis timeout generates appropriate fixes."""
        evidence = {
            "severity": "P1",
            "uses_redis": True,
            "timeout_errors": 3
        }

        suggestions = [{
            "file": ".env",
            "diff": "REDIS_TIMEOUT=1 -> REDIS_TIMEOUT=5",
            "rationale": "Increase timeout"
        }]

        plan = generate_remediation_plan("Redis timeout", evidence, suggestions)

        # Should include short-term fixes
        assert len(plan["short_term_fixes"]) > 0

        # Should include suggestion from fixer agent
        assert any(".env" in fix.get("file", "") for fix in plan["short_term_fixes"])

    def test_long_term_fixes_for_redis(self):
        """Test long-term fixes are generated for Redis issues."""
        evidence = {
            "severity": "P1",
            "uses_redis": True,
            "timeout_errors": 3
        }

        plan = generate_remediation_plan("Redis timeout", evidence, [])

        # Should have long-term fixes
        assert len(plan["long_term_fixes"]) > 0

        # Should include circuit breaker
        assert any("circuit breaker" in fix["action"].lower() for fix in plan["long_term_fixes"])

        # Should include monitoring
        assert any("monitoring" in fix["action"].lower() for fix in plan["long_term_fixes"])

    def test_verification_steps_for_p0(self):
        """Test verification steps for P0 severity."""
        evidence = {"severity": "P0"}

        plan = generate_remediation_plan("Critical issue", evidence, [])

        # Should have verification steps
        assert len(plan["verification_steps"]) > 0

        # P0 should have specific metrics
        assert any("error rate" in step.lower() for step in plan["verification_steps"])


class TestRemediationFormatting:
    """Test remediation plan formatting."""

    def test_format_immediate_actions(self):
        """Test immediate actions formatting."""
        plan = {
            "immediate_actions": [{
                "step": 1,
                "action": "Check Redis status",
                "command": "redis-cli ping",
                "risk": "LOW",
                "estimated_time": "30 seconds",
                "rationale": "Verify Redis is running"
            }]
        }

        output = format_remediation_output(plan)

        assert "[!] IMMEDIATE ACTIONS" in output
        assert "Check Redis status" in output
        assert "redis-cli ping" in output
        assert "Risk: LOW" in output

    def test_format_short_term_fixes(self):
        """Test short-term fixes formatting."""
        plan = {
            "short_term_fixes": [{
                "step": 1,
                "action": "Update Redis config",
                "file": ".env",
                "change": "REDIS_TIMEOUT=5",
                "rationale": "Increase timeout",
                "risk": "LOW"
            }]
        }

        output = format_remediation_output(plan)

        assert "[~] SHORT-TERM FIXES" in output
        assert "Update Redis config" in output
        assert ".env" in output

    def test_format_long_term_fixes(self):
        """Test long-term fixes formatting."""
        plan = {
            "long_term_fixes": [{
                "action": "Implement circuit breaker",
                "estimated_effort": "2-3 days",
                "rationale": "Prevent cascading failures"
            }]
        }

        output = format_remediation_output(plan)

        assert "[+] LONG-TERM FIXES" in output
        assert "circuit breaker" in output
        assert "2-3 days" in output

    def test_format_verification_steps(self):
        """Test verification steps formatting."""
        plan = {
            "verification_steps": [
                "Monitor error rate",
                "Check Redis connections"
            ]
        }

        output = format_remediation_output(plan)

        assert "[v] VERIFICATION STEPS" in output
        assert "Monitor error rate" in output
        assert "Check Redis connections" in output

    def test_format_empty_plan(self):
        """Test formatting empty plan."""
        plan = {}

        output = format_remediation_output(plan)

        # Should return empty string or minimal output
        assert len(output) < 50


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
