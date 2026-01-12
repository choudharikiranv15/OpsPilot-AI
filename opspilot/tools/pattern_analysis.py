"""Production error pattern recognition."""

import re
from typing import Dict, List
from collections import Counter


def identify_error_patterns(logs: str) -> Dict:
    """
    Identify common production error patterns.

    Args:
        logs: Raw log text

    Returns:
        Dictionary containing identified patterns and severity
    """
    if not logs:
        return {}

    patterns = {
        "http_errors": _extract_http_errors(logs),
        "exceptions": _extract_exceptions(logs),
        "database_errors": _extract_database_errors(logs),
        "timeout_errors": _extract_timeout_errors(logs),
        "memory_errors": _extract_memory_errors(logs),
        "stack_traces": _extract_stack_traces(logs)
    }

    # Add severity assessment
    patterns["severity"] = _assess_severity(patterns)
    patterns["error_count"] = _count_total_errors(patterns)

    return {k: v for k, v in patterns.items() if v}


def _extract_http_errors(logs: str) -> Dict[str, int]:
    """Extract HTTP error codes (4xx, 5xx)."""
    http_pattern = r'\b(4\d{2}|5\d{2})\b'
    codes = re.findall(http_pattern, logs)
    return dict(Counter(codes)) if codes else {}


def _extract_exceptions(logs: str) -> List[str]:
    """Extract exception types."""
    exception_patterns = [
        r'(\w+Exception):',
        r'(\w+Error):',
        r'Traceback.*?(\w+Error)',
    ]

    exceptions = []
    for pattern in exception_patterns:
        matches = re.findall(pattern, logs, re.MULTILINE)
        exceptions.extend(matches)

    # Return top 10 unique exceptions
    return list(set(exceptions))[:10]


def _extract_database_errors(logs: str) -> List[str]:
    """Extract database-related errors."""
    db_patterns = [
        r'(connection refused|connection timeout|connection lost)',
        r'(deadlock|lock timeout)',
        r'(too many connections)',
        r'(database.*?error)',
    ]

    db_errors = []
    for pattern in db_patterns:
        matches = re.findall(pattern, logs, re.IGNORECASE)
        db_errors.extend(matches)

    return list(set(db_errors))[:10]


def _extract_timeout_errors(logs: str) -> int:
    """Count timeout-related errors."""
    timeout_pattern = r'timeout|timed out|time out'
    return len(re.findall(timeout_pattern, logs, re.IGNORECASE))


def _extract_memory_errors(logs: str) -> List[str]:
    """Extract memory-related errors."""
    memory_patterns = [
        r'OutOfMemoryError',
        r'MemoryError',
        r'out of memory',
        r'OOM',
        r'memory limit exceeded'
    ]

    memory_errors = []
    for pattern in memory_patterns:
        if re.search(pattern, logs, re.IGNORECASE):
            memory_errors.append(pattern)

    return memory_errors


def _extract_stack_traces(logs: str) -> int:
    """Count stack traces."""
    trace_patterns = [
        r'Traceback \(most recent call last\)',
        r'at \w+\.\w+\(',
        r'^\s+at .*\(.*:\d+\)',
    ]

    count = 0
    for pattern in trace_patterns:
        count += len(re.findall(pattern, logs, re.MULTILINE))

    return count


def _assess_severity(patterns: Dict) -> str:
    """
    Assess overall severity based on error patterns.

    P0 = Critical (production down)
    P1 = High (major functionality broken)
    P2 = Medium (degraded performance)
    P3 = Low (minor issues)
    """
    http_5xx = sum(
        count for code, count in patterns.get("http_errors", {}).items()
        if code.startswith('5')
    )
    memory_errors = len(patterns.get("memory_errors", []))
    timeout_count = patterns.get("timeout_errors", 0)
    db_errors = len(patterns.get("database_errors", []))

    # P0: Multiple 5xx errors or OOM
    if http_5xx > 10 or memory_errors > 0:
        return "P0"

    # P1: Significant 5xx or database errors
    if http_5xx > 5 or db_errors > 0:
        return "P1"

    # P2: Moderate errors or timeouts
    if http_5xx > 0 or timeout_count > 5:
        return "P2"

    # P3: Minor 4xx errors only
    return "P3"


def _count_total_errors(patterns: Dict) -> int:
    """Count total errors across all patterns."""
    count = 0

    # HTTP errors
    count += sum(patterns.get("http_errors", {}).values())

    # Exceptions
    count += len(patterns.get("exceptions", []))

    # Database errors
    count += len(patterns.get("database_errors", []))

    # Timeouts
    count += patterns.get("timeout_errors", 0)

    # Memory errors
    count += len(patterns.get("memory_errors", []))

    return count


def build_error_timeline(logs: str) -> Dict:
    """
    Build a timeline of when errors occurred.

    Args:
        logs: Raw log text with timestamps

    Returns:
        Timeline information including first/last seen, occurrences
    """
    # Extract timestamps (ISO format or common log formats)
    timestamp_pattern = r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})'
    timestamps = re.findall(timestamp_pattern, logs)

    if not timestamps:
        return {}

    return {
        "first_seen": timestamps[0] if timestamps else "unknown",
        "last_seen": timestamps[-1] if timestamps else "unknown",
        "total_occurrences": len(timestamps),
        "time_range": f"{timestamps[0]} to {timestamps[-1]}" if len(timestamps) > 1 else "single occurrence"
    }
