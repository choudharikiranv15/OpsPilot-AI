"""
Structured troubleshooting workflow following real SRE debugging patterns.

Standard Pattern:
1. Logs → Find what broke (symptoms)
2. Recent Changes → When did it break (timeline)
3. Similar Incidents → Has this happened before (historical data)
4. Stack Trace → Where did it break (location)
5. Environment → Configuration issues (env vars, secrets)
6. Dependencies → Version conflicts (packages)
7. Resources → System limits (memory, connections, disk)
8. External Services → Third-party failures (APIs, databases)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TroubleshootingPhase(Enum):
    """Phases of troubleshooting workflow."""

    LOGS_ANALYSIS = "logs_analysis"
    RECENT_CHANGES = "recent_changes"
    SIMILAR_INCIDENTS = "similar_incidents"
    STACK_TRACE = "stack_trace"
    ENVIRONMENT_CHECK = "environment_check"
    DEPENDENCY_CHECK = "dependency_check"
    RESOURCE_CHECK = "resource_check"
    EXTERNAL_SERVICES = "external_services"
    ROOT_CAUSE = "root_cause"
    REMEDIATION = "remediation"


@dataclass
class TroubleshootingContext:
    """Context gathered during troubleshooting workflow."""

    # Phase 1: What broke? (Symptoms)
    error_logs: list[str] = field(default_factory=list)
    error_count: int = 0
    severity: str | None = None
    first_occurrence: str | None = None
    last_occurrence: str | None = None

    # Phase 2: When did it break? (Timeline)
    recent_deployments: list[dict] = field(default_factory=list)
    recent_commits: list[dict] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)

    # Phase 3: Has this happened before? (Historical)
    similar_incidents: list[dict] = field(default_factory=list)
    known_patterns: list[str] = field(default_factory=list)

    # Phase 4: Where did it break? (Location)
    stack_traces: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    affected_functions: list[str] = field(default_factory=list)

    # Phase 5: Configuration issues? (Environment)
    missing_env_vars: list[str] = field(default_factory=list)
    env_var_count: int = 0
    config_files: list[str] = field(default_factory=list)

    # Phase 6: Version conflicts? (Dependencies)
    dependencies: list[str] = field(default_factory=list)
    outdated_packages: list[str] = field(default_factory=list)
    conflicting_versions: list[dict] = field(default_factory=list)

    # Phase 7: Resource exhaustion? (System)
    memory_errors: bool = False
    disk_errors: bool = False
    connection_errors: bool = False
    timeout_errors: bool = False

    # Phase 8: External failures? (Third-party)
    external_api_errors: list[str] = field(default_factory=list)
    database_errors: list[str] = field(default_factory=list)
    network_errors: list[str] = field(default_factory=list)

    # Final phases
    root_cause_hypothesis: str | None = None
    confidence: float = 0.0
    remediation_steps: list[str] = field(default_factory=list)


@dataclass
class TroubleshootingResult:
    """Result of troubleshooting workflow."""

    phase_completed: TroubleshootingPhase
    findings: dict[str, Any]
    confidence: float
    should_continue: bool
    next_phase: TroubleshootingPhase | None = None
    reasoning: str | None = None


class TroubleshootingWorkflow:
    """
    Structured troubleshooting workflow following real SRE patterns.

    Follows the pattern:
    1. Start with symptoms (logs)
    2. Establish timeline (recent changes)
    3. Check history (similar incidents)
    4. Pinpoint location (stack traces)
    5. Verify config (environment)
    6. Check dependencies
    7. Check resources
    8. Check external services
    9. Form hypothesis
    10. Generate remediation
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.context = TroubleshootingContext()
        self.current_phase = TroubleshootingPhase.LOGS_ANALYSIS
        self.phase_results: dict[TroubleshootingPhase, TroubleshootingResult] = {}

    def execute(self) -> TroubleshootingContext:
        """
        Execute full troubleshooting workflow in order.

        Each phase builds on previous phases and decides whether to continue.
        """
        workflow_phases = [
            (TroubleshootingPhase.LOGS_ANALYSIS, self._analyze_logs),
            (TroubleshootingPhase.RECENT_CHANGES, self._check_recent_changes),
            (TroubleshootingPhase.SIMILAR_INCIDENTS, self._check_similar_incidents),
            (TroubleshootingPhase.STACK_TRACE, self._analyze_stack_traces),
            (TroubleshootingPhase.ENVIRONMENT_CHECK, self._check_environment),
            (TroubleshootingPhase.DEPENDENCY_CHECK, self._check_dependencies),
            (TroubleshootingPhase.RESOURCE_CHECK, self._check_resources),
            (TroubleshootingPhase.EXTERNAL_SERVICES, self._check_external_services),
            (TroubleshootingPhase.ROOT_CAUSE, self._form_hypothesis),
            (TroubleshootingPhase.REMEDIATION, self._generate_remediation),
        ]

        for phase, phase_func in workflow_phases:
            self.current_phase = phase
            result = phase_func()
            self.phase_results[phase] = result

            # Early exit if we have high confidence or phase says stop
            if not result.should_continue:
                break

            # If we found root cause with high confidence, skip to remediation
            if phase == TroubleshootingPhase.ROOT_CAUSE and result.confidence >= 0.8:
                continue

        return self.context

    def _analyze_logs(self) -> TroubleshootingResult:
        """
        Phase 1: Analyze logs to identify symptoms.

        Priority checks:
        1. Recent errors (last 1 hour most important)
        2. Error frequency (increasing = worse)
        3. Error severity (FATAL > ERROR > WARN)
        4. Error patterns (repeated = systematic issue)
        """
        from opspilot.context.logs import read_logs
        from opspilot.tools.pattern_analysis import identify_error_patterns

        # Read logs with focus on recent errors
        logs = read_logs(self.project_root)

        if not logs:
            return TroubleshootingResult(
                phase_completed=TroubleshootingPhase.LOGS_ANALYSIS,
                findings={"logs_found": False},
                confidence=0.0,
                should_continue=True,
                next_phase=TroubleshootingPhase.ENVIRONMENT_CHECK,
                reasoning="No logs found, skip to environment check",
            )

        # Analyze error patterns
        patterns = identify_error_patterns(logs)

        self.context.error_logs = patterns.get("error_lines", [])
        self.context.error_count = patterns.get("error_count", 0)
        self.context.severity = patterns.get("severity", "P3")
        self.context.first_occurrence = patterns.get("timeline", {}).get("first_seen")
        self.context.last_occurrence = patterns.get("timeline", {}).get("last_seen")

        # Extract specific error types
        self.context.memory_errors = "memory" in patterns.get("exceptions", [])
        self.context.timeout_errors = patterns.get("timeout_errors", 0) > 0
        self.context.connection_errors = (
            "connection" in str(patterns.get("exceptions", [])).lower()
        )

        confidence = 0.9 if self.context.error_count > 0 else 0.3

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.LOGS_ANALYSIS,
            findings={
                "error_count": self.context.error_count,
                "severity": self.context.severity,
            },
            confidence=confidence,
            should_continue=True,
            next_phase=TroubleshootingPhase.RECENT_CHANGES,
            reasoning=f"Found {self.context.error_count} errors with severity {self.context.severity}",
        )

    def _check_recent_changes(self) -> TroubleshootingResult:
        """
        Phase 2: Check for recent changes that might have caused the issue.

        Timeline analysis:
        1. Recent deployments (last 24 hours critical)
        2. Recent commits (what changed)
        3. Changed files (which files touched)
        4. Correlate with first error occurrence
        """
        from opspilot.context.deployment_history import analyze_deployment_impact

        # Analyze last 48 hours of deployments
        deployment_info = analyze_deployment_impact(self.project_root, since_hours=48)

        if deployment_info and deployment_info.get("has_recent_changes"):
            self.context.recent_deployments = deployment_info.get("deployments", [])
            self.context.recent_commits = deployment_info.get("commits", [])
            self.context.changed_files = deployment_info.get("changed_files", [])

            # High confidence if error started after recent deployment
            confidence = 0.8 if len(self.context.recent_commits) > 0 else 0.3

            return TroubleshootingResult(
                phase_completed=TroubleshootingPhase.RECENT_CHANGES,
                findings={"recent_commits": len(self.context.recent_commits)},
                confidence=confidence,
                should_continue=True,
                next_phase=TroubleshootingPhase.SIMILAR_INCIDENTS,
                reasoning="Recent changes detected, correlating with errors",
            )

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.RECENT_CHANGES,
            findings={"recent_commits": 0},
            confidence=0.3,
            should_continue=True,
            next_phase=TroubleshootingPhase.SIMILAR_INCIDENTS,
            reasoning="No recent deployments found",
        )

    def _check_similar_incidents(self) -> TroubleshootingResult:
        """
        Phase 3: Check for similar incidents in the past.

        Historical analysis:
        1. Query memory for similar error patterns
        2. Check if this is a recurring issue
        3. Look for previous fixes that worked
        """
        from opspilot.memory import find_similar_issues

        similar = find_similar_issues(self.project_root, threshold=0.6)

        if similar:
            self.context.similar_incidents = similar
            self.context.known_patterns = [s.get("hypothesis") for s in similar]

            # High confidence if we've seen this before with fixes
            confidence = 0.9 if len(similar) > 0 else 0.0

            return TroubleshootingResult(
                phase_completed=TroubleshootingPhase.SIMILAR_INCIDENTS,
                findings={"similar_count": len(similar)},
                confidence=confidence,
                should_continue=confidence < 0.8,  # If we know the fix, fast-track
                next_phase=TroubleshootingPhase.REMEDIATION
                if confidence >= 0.8
                else TroubleshootingPhase.STACK_TRACE,
                reasoning=f"Found {len(similar)} similar past incidents",
            )

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.SIMILAR_INCIDENTS,
            findings={"similar_count": 0},
            confidence=0.0,
            should_continue=True,
            next_phase=TroubleshootingPhase.STACK_TRACE,
            reasoning="No similar incidents found, continue investigation",
        )

    def _analyze_stack_traces(self) -> TroubleshootingResult:
        """
        Phase 4: Analyze stack traces to pinpoint error location.

        Location analysis:
        1. Extract stack traces from logs
        2. Identify affected files
        3. Identify affected functions
        4. Map to recent changes
        """
        # Extract stack traces from error logs
        stack_traces = []
        affected_files = set()

        for log_line in self.context.error_logs:
            # Simple stack trace detection (can be improved with regex)
            if "Traceback" in log_line or "at " in log_line or "File " in log_line:
                stack_traces.append(log_line)

                # Extract file names
                if ".py" in log_line or ".js" in log_line or ".java" in log_line:
                    # Simplified extraction
                    for word in log_line.split():
                        if any(
                            ext in word for ext in [".py", ".js", ".java", ".go", ".rb"]
                        ):
                            affected_files.add(word.strip('",()[]'))

        self.context.stack_traces = stack_traces
        self.context.affected_files = list(affected_files)

        confidence = 0.8 if len(affected_files) > 0 else 0.3

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.STACK_TRACE,
            findings={"affected_files": len(affected_files)},
            confidence=confidence,
            should_continue=True,
            next_phase=TroubleshootingPhase.ENVIRONMENT_CHECK,
            reasoning=f"Identified {len(affected_files)} affected files",
        )

    def _check_environment(self) -> TroubleshootingResult:
        """
        Phase 5: Check environment configuration.

        Config checks:
        1. Missing environment variables
        2. Invalid configurations
        3. Secrets/credentials issues
        """
        from opspilot.context.env import read_env_names
        from opspilot.tools.env_tools import find_missing_env

        env = read_env_names(self.project_root)
        self.context.env_var_count = len(env)

        # Check for commonly missing env vars
        missing = find_missing_env(env)
        self.context.missing_env_vars = missing

        confidence = 0.7 if len(missing) > 0 else 0.3

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.ENVIRONMENT_CHECK,
            findings={"missing_vars": len(missing), "total_vars": len(env)},
            confidence=confidence,
            should_continue=True,
            next_phase=TroubleshootingPhase.DEPENDENCY_CHECK,
            reasoning=f"Found {len(missing)} missing environment variables",
        )

    def _check_dependencies(self) -> TroubleshootingResult:
        """
        Phase 6: Check for dependency issues.

        Dependency checks:
        1. Package versions
        2. Conflicting dependencies
        3. Missing dependencies
        """
        from opspilot.context.deps import read_dependencies

        deps = read_dependencies(self.project_root)
        self.context.dependencies = deps

        # Simple check: if we have database/redis errors, check for those deps
        has_redis = any("redis" in d.lower() for d in deps)
        has_db_errors = "database" in str(self.context.error_logs).lower()

        confidence = 0.6 if (has_db_errors and not has_redis) else 0.3

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.DEPENDENCY_CHECK,
            findings={"dependency_count": len(deps)},
            confidence=confidence,
            should_continue=True,
            next_phase=TroubleshootingPhase.RESOURCE_CHECK,
            reasoning=f"Analyzed {len(deps)} dependencies",
        )

    def _check_resources(self) -> TroubleshootingResult:
        """
        Phase 7: Check for resource exhaustion.

        Resource checks:
        1. Memory errors
        2. Disk space
        3. Connection limits
        4. Timeouts
        """
        # Already extracted from logs in phase 1
        resource_issues = (
            self.context.memory_errors
            or self.context.timeout_errors
            or self.context.connection_errors
        )

        confidence = 0.8 if resource_issues else 0.2

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.RESOURCE_CHECK,
            findings={
                "memory_errors": self.context.memory_errors,
                "timeout_errors": self.context.timeout_errors,
                "connection_errors": self.context.connection_errors,
            },
            confidence=confidence,
            should_continue=True,
            next_phase=TroubleshootingPhase.EXTERNAL_SERVICES,
            reasoning="Resource check completed",
        )

    def _check_external_services(self) -> TroubleshootingResult:
        """
        Phase 8: Check for external service failures.

        External checks:
        1. API failures
        2. Database connectivity
        3. Network issues
        """
        # Extract from error logs
        error_text = " ".join(self.context.error_logs).lower()

        self.context.external_api_errors = ["api" in error_text, "http" in error_text]
        self.context.database_errors = ["database" in error_text, "sql" in error_text]
        self.context.network_errors = ["network" in error_text, "dns" in error_text]

        has_external_issues = any(
            [
                any(self.context.external_api_errors),
                any(self.context.database_errors),
                any(self.context.network_errors),
            ]
        )

        confidence = 0.7 if has_external_issues else 0.2

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.EXTERNAL_SERVICES,
            findings={"external_issues": has_external_issues},
            confidence=confidence,
            should_continue=True,
            next_phase=TroubleshootingPhase.ROOT_CAUSE,
            reasoning="External service check completed",
        )

    def _form_hypothesis(self) -> TroubleshootingResult:
        """
        Phase 9: Form root cause hypothesis based on all evidence.

        Combines findings from all phases to determine root cause.
        """
        # Prioritize evidence by confidence
        hypotheses = []

        # Check each phase for high-confidence findings
        if self.context.similar_incidents:
            hypotheses.append(
                (
                    0.9,
                    self.context.similar_incidents[0].get("hypothesis"),
                    "Based on similar past incident",
                )
            )

        if self.context.recent_commits and self.context.affected_files:
            hypotheses.append(
                (
                    0.8,
                    f"Code change in {self.context.affected_files[0]} caused regression",
                    "Recent deployment correlates with error start",
                )
            )

        if self.context.missing_env_vars:
            hypotheses.append(
                (
                    0.7,
                    f"Missing environment variable: {self.context.missing_env_vars[0]}",
                    "Configuration issue",
                )
            )

        if self.context.memory_errors:
            hypotheses.append(
                (0.8, "Memory exhaustion or leak", "Memory-related errors detected")
            )

        if self.context.timeout_errors:
            hypotheses.append(
                (
                    0.7,
                    "Network timeout or slow external service",
                    "Timeout errors detected",
                )
            )

        # Default hypothesis if nothing specific found
        if not hypotheses:
            hypotheses.append(
                (
                    0.4,
                    "Undetermined runtime issue",
                    "Insufficient evidence for specific hypothesis",
                )
            )

        # Pick highest confidence hypothesis
        hypotheses.sort(reverse=True)
        confidence, hypothesis, reasoning = hypotheses[0]

        self.context.root_cause_hypothesis = hypothesis
        self.context.confidence = confidence

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.ROOT_CAUSE,
            findings={"hypothesis": hypothesis},
            confidence=confidence,
            should_continue=True,
            next_phase=TroubleshootingPhase.REMEDIATION,
            reasoning=reasoning,
        )

    def _generate_remediation(self) -> TroubleshootingResult:
        """
        Phase 10: Generate remediation steps.
        """
        steps = []

        # Immediate actions based on findings
        if self.context.missing_env_vars:
            for var in self.context.missing_env_vars[:3]:
                steps.append(f"Set environment variable: {var}")

        if self.context.recent_commits:
            steps.append("Review recent code changes for regressions")
            if self.context.affected_files:
                steps.append(f"Focus on file: {self.context.affected_files[0]}")

        if self.context.memory_errors:
            steps.append("Increase memory allocation")
            steps.append("Check for memory leaks")

        if self.context.timeout_errors:
            steps.append("Increase timeout settings")
            steps.append("Investigate slow external services")

        if self.context.connection_errors:
            steps.append("Check network connectivity")
            steps.append("Verify database/service availability")

        # Verification steps
        steps.append("Monitor error rate after applying fixes")
        steps.append("Check application metrics dashboard")

        self.context.remediation_steps = steps

        return TroubleshootingResult(
            phase_completed=TroubleshootingPhase.REMEDIATION,
            findings={"steps": len(steps)},
            confidence=self.context.confidence,
            should_continue=False,  # Workflow complete
            reasoning=f"Generated {len(steps)} remediation steps",
        )

    def get_summary(self) -> dict[str, Any]:
        """Get workflow execution summary."""
        return {
            "phases_completed": [p.value for p in self.phase_results],
            "root_cause": self.context.root_cause_hypothesis,
            "confidence": self.context.confidence,
            "severity": self.context.severity,
            "error_count": self.context.error_count,
            "similar_incidents": len(self.context.similar_incidents),
            "remediation_steps": len(self.context.remediation_steps),
            "context": self.context,
        }
