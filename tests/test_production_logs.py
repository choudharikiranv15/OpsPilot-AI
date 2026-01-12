"""Unit tests for production log fetching."""

import pytest
from unittest.mock import patch, Mock, MagicMock
from opspilot.context.production_logs import (
    fetch_logs_from_file,
    fetch_logs_from_url,
    fetch_logs_from_s3,
    fetch_logs_from_kubectl,
    auto_detect_and_fetch
)


class TestLocalFileLogFetching:
    """Test local file log reading."""

    def test_read_existing_file(self, tmp_path):
        """Test reading logs from existing file."""
        log_file = tmp_path / "test.log"
        log_content = "ERROR: Test error\nWARNING: Test warning"
        log_file.write_text(log_content)

        result = fetch_logs_from_file(str(log_file))
        assert result == log_content

    def test_read_nonexistent_file(self):
        """Test reading from non-existent file."""
        result = fetch_logs_from_file("/nonexistent/path/file.log")
        assert result is None


class TestURLLogFetching:
    """Test HTTP/HTTPS log fetching."""

    @patch('opspilot.context.production_logs.requests.get')
    def test_fetch_from_url_success(self, mock_get):
        """Test successful URL log fetch."""
        mock_response = Mock()
        mock_response.text = "ERROR: Production error"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = fetch_logs_from_url("https://example.com/logs/app.log")
        assert result == "ERROR: Production error"
        mock_get.assert_called_once()

    @patch('opspilot.context.production_logs.requests.get')
    def test_fetch_from_url_failure(self, mock_get):
        """Test URL fetch failure."""
        mock_get.side_effect = Exception("Connection failed")

        result = fetch_logs_from_url("https://example.com/logs/app.log")
        assert result is None


class TestS3LogFetching:
    """Test S3 log fetching."""

    @patch('opspilot.context.production_logs.subprocess.run')
    def test_fetch_from_s3_success(self, mock_run):
        """Test successful S3 log fetch."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "S3 log content"
        mock_run.return_value = mock_result

        result = fetch_logs_from_s3("my-bucket", "logs/app.log")
        assert result == "S3 log content"

    @patch('opspilot.context.production_logs.subprocess.run')
    def test_fetch_from_s3_failure(self, mock_run):
        """Test S3 fetch failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Access denied"
        mock_run.return_value = mock_result

        result = fetch_logs_from_s3("my-bucket", "logs/app.log")
        assert result is None


class TestKubernetesLogFetching:
    """Test Kubernetes log fetching."""

    @patch('opspilot.context.production_logs.subprocess.run')
    def test_fetch_kubectl_logs_success(self, mock_run):
        """Test successful kubectl log fetch."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Pod log content"
        mock_run.return_value = mock_result

        result = fetch_logs_from_kubectl("production", "api-server")
        assert result == "Pod log content"

    @patch('opspilot.context.production_logs.subprocess.run')
    def test_fetch_kubectl_logs_with_container(self, mock_run):
        """Test kubectl log fetch with container name."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Container log content"
        mock_run.return_value = mock_result

        result = fetch_logs_from_kubectl("production", "api-server", "app")
        assert result == "Container log content"


class TestAutoDetection:
    """Test automatic log source detection."""

    @patch('opspilot.context.production_logs.fetch_logs_from_url')
    def test_auto_detect_https_url(self, mock_fetch):
        """Test auto-detection of HTTPS URL."""
        mock_fetch.return_value = "URL logs"

        result = auto_detect_and_fetch("https://example.com/logs/app.log")
        assert result == "URL logs"
        mock_fetch.assert_called_once()

    @patch('opspilot.context.production_logs.fetch_logs_from_s3')
    def test_auto_detect_s3_path(self, mock_fetch):
        """Test auto-detection of S3 path."""
        mock_fetch.return_value = "S3 logs"

        result = auto_detect_and_fetch("s3://my-bucket/logs/app.log")
        assert result == "S3 logs"
        mock_fetch.assert_called_with("my-bucket", "logs/app.log")

    @patch('opspilot.context.production_logs.fetch_logs_from_kubectl')
    def test_auto_detect_kubernetes_path(self, mock_fetch):
        """Test auto-detection of Kubernetes path."""
        mock_fetch.return_value = "K8s logs"

        result = auto_detect_and_fetch("k8s://production/api-server")
        assert result == "K8s logs"
        mock_fetch.assert_called_with("production", "api-server")

    @patch('opspilot.context.production_logs.fetch_logs_from_file')
    def test_auto_detect_local_file(self, mock_fetch):
        """Test auto-detection of local file path."""
        mock_fetch.return_value = "Local logs"

        result = auto_detect_and_fetch("/var/log/app.log")
        assert result == "Local logs"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
