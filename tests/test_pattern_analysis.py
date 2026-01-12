"""Unit tests for error pattern analysis."""

import pytest
from opspilot.tools.pattern_analysis import (
    identify_error_patterns,
    build_error_timeline,
    _assess_severity,
    _extract_http_errors,
    _extract_exceptions,
    _extract_database_errors,
    _extract_timeout_errors,
    _extract_memory_errors
)


class TestErrorPatternDetection:
    """Test error pattern identification."""

    def test_http_error_detection(self):
        """Test HTTP error code extraction."""
        logs = """
        2026-01-12 10:15:23 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:24 ERROR HTTP 503 - Service Unavailable
        2026-01-12 10:15:25 ERROR HTTP 404 - Not Found
        2026-01-12 10:15:26 ERROR HTTP 500 - Internal Server Error
        """

        http_errors = _extract_http_errors(logs)
        assert http_errors['500'] == 2
        assert http_errors['503'] == 1
        assert http_errors['404'] == 1

    def test_exception_detection(self):
        """Test Python exception extraction."""
        logs = """
        2026-01-12 10:15:23 ERROR ConnectionError: Connection refused
        2026-01-12 10:15:24 ERROR TimeoutError: Request timed out
        2026-01-12 10:15:25 ERROR ValueError: Invalid input
        """

        exceptions = _extract_exceptions(logs)
        assert 'ConnectionError' in exceptions
        assert 'TimeoutError' in exceptions
        assert 'ValueError' in exceptions

    def test_database_error_detection(self):
        """Test database error extraction."""
        logs = """
        2026-01-12 10:15:23 ERROR psycopg2.OperationalError: server closed connection
        2026-01-12 10:15:24 ERROR redis.exceptions.ConnectionError: Connection refused
        2026-01-12 10:15:25 ERROR Connection timeout to database
        """

        db_errors = _extract_database_errors(logs)
        assert len(db_errors) == 3
        assert any('psycopg2' in err for err in db_errors)
        assert any('redis' in err for err in db_errors)

    def test_timeout_error_detection(self):
        """Test timeout error counting."""
        logs = """
        2026-01-12 10:15:23 ERROR Timeout waiting for response
        2026-01-12 10:15:24 ERROR Connection timeout
        2026-01-12 10:15:25 ERROR Request timed out
        """

        timeout_count = _extract_timeout_errors(logs)
        assert timeout_count == 3

    def test_memory_error_detection(self):
        """Test memory error extraction."""
        logs = """
        2026-01-12 10:15:23 ERROR MemoryError: Out of memory
        2026-01-12 10:15:24 ERROR Out of memory
        """

        memory_errors = _extract_memory_errors(logs)
        assert len(memory_errors) == 2


class TestSeverityClassification:
    """Test severity assessment logic."""

    def test_p0_classification_5xx_errors(self):
        """Test P0 classification with 10+ 5xx errors."""
        patterns = {
            "http_errors": {"500": 12, "503": 2},
            "exceptions": [],
            "database_errors": [],
            "timeout_errors": 0,
            "memory_errors": []
        }

        severity = _assess_severity(patterns)
        assert severity == "P0"

    def test_p0_classification_memory_errors(self):
        """Test P0 classification with memory errors."""
        patterns = {
            "http_errors": {"500": 2},
            "exceptions": [],
            "database_errors": [],
            "timeout_errors": 0,
            "memory_errors": ["MemoryError", "out of memory"]
        }

        severity = _assess_severity(patterns)
        assert severity == "P0"

    def test_p1_classification(self):
        """Test P1 classification with database errors."""
        patterns = {
            "http_errors": {"500": 6},
            "exceptions": [],
            "database_errors": ["psycopg2.OperationalError"],
            "timeout_errors": 0,
            "memory_errors": []
        }

        severity = _assess_severity(patterns)
        assert severity == "P1"

    def test_p2_classification(self):
        """Test P2 classification with some 5xx errors."""
        patterns = {
            "http_errors": {"500": 3},
            "exceptions": [],
            "database_errors": [],
            "timeout_errors": 2,
            "memory_errors": []
        }

        severity = _assess_severity(patterns)
        assert severity == "P2"

    def test_p3_classification(self):
        """Test P3 classification with only 4xx errors."""
        patterns = {
            "http_errors": {"404": 5, "400": 3},
            "exceptions": [],
            "database_errors": [],
            "timeout_errors": 0,
            "memory_errors": []
        }

        severity = _assess_severity(patterns)
        assert severity == "P3"


class TestTimelineAnalysis:
    """Test error timeline extraction."""

    def test_timeline_extraction(self):
        """Test timeline first/last seen extraction."""
        logs = """
        2026-01-12 10:15:23 ERROR First error
        2026-01-12 10:15:30 ERROR Second error
        2026-01-12 10:16:50 ERROR Last error
        """

        timeline = build_error_timeline(logs)
        assert timeline['first_seen'] == '2026-01-12 10:15:23'
        assert timeline['last_seen'] == '2026-01-12 10:16:50'
        assert timeline['total_occurrences'] == 3

    def test_timeline_no_timestamps(self):
        """Test timeline with no timestamps."""
        logs = "ERROR Some error without timestamp"

        timeline = build_error_timeline(logs)
        assert timeline['first_seen'] == 'unknown'
        assert timeline['last_seen'] == 'unknown'


class TestIntegration:
    """Integration tests for full pattern analysis."""

    def test_full_pattern_analysis(self):
        """Test complete pattern identification."""
        logs = """
        2026-01-12 10:15:23 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:24 ERROR redis.exceptions.ConnectionError: Connection refused
        2026-01-12 10:15:25 ERROR HTTP 503 - Service Unavailable
        2026-01-12 10:15:26 ERROR TimeoutError: Request timed out
        2026-01-12 10:15:27 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:28 ERROR MemoryError: Out of memory
        2026-01-12 10:15:29 ERROR psycopg2.OperationalError: server closed
        2026-01-12 10:15:30 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:31 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:32 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:33 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:34 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:35 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:36 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:37 ERROR HTTP 500 - Internal Server Error
        2026-01-12 10:15:38 ERROR HTTP 500 - Internal Server Error
        """

        patterns = identify_error_patterns(logs)

        # Verify HTTP errors detected
        assert patterns['http_errors']['500'] >= 10
        assert patterns['http_errors']['503'] == 1

        # Verify severity is P0 (10+ 5xx + memory error)
        assert patterns['severity'] == 'P0'

        # Verify exceptions detected
        assert 'TimeoutError' in patterns['exceptions']
        assert 'MemoryError' in patterns['exceptions']

        # Verify database errors detected
        assert len(patterns['database_errors']) >= 2

        # Verify error count
        assert patterns['error_count'] > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
