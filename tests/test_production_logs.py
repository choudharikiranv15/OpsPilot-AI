"""Tests for explicit log sources (--log-source)."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import Mock, patch

import pytest
import requests

from opspilot import proc
from opspilot.context import production_logs as pl
from opspilot.context.production_logs import (
    LogSourceError,
    auto_detect_and_fetch,
    fetch_logs_from_file,
    parse_cloudwatch_source,
)


class TestFileSource:
    def test_reads_file(self, tmp_path):
        path = tmp_path / "service.out"
        path.write_bytes(b"ERROR: boom\n")
        assert fetch_logs_from_file(str(path)) == "ERROR: boom\n"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(LogSourceError, match="not found"):
            fetch_logs_from_file(str(tmp_path / "missing.log"))

    def test_large_file_is_tail_bounded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pl, "MAX_FETCH_BYTES", 100)
        path = tmp_path / "big.log"
        path.write_text("".join(f"line {i}\n" for i in range(1000)), encoding="utf-8")
        text = fetch_logs_from_file(str(path))
        assert len(text) <= 100
        assert text.rstrip().endswith("line 999")


class TestUrlSource:
    @patch("opspilot.context.production_logs.requests.get")
    def test_fetch_success_keeps_tail(self, mock_get, monkeypatch):
        monkeypatch.setattr(pl, "MAX_FETCH_BYTES", 10)
        response = Mock()
        response.iter_content.return_value = [b"0123456789", b"abcdefghij"]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        mock_get.return_value = response
        assert auto_detect_and_fetch("https://logs.example/app.log") == "abcdefghij"
        assert mock_get.call_args.kwargs["stream"] is True

    @patch("opspilot.context.production_logs.requests.get")
    def test_fetch_failure_raises(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("down")
        with pytest.raises(LogSourceError, match="Failed to fetch"):
            auto_detect_and_fetch("https://logs.example/app.log")


class TestSourceValidation:
    @pytest.mark.parametrize(
        "source",
        [
            "k8s://prod/--kubeconfig=/tmp/x",
            "k8s://Prod_NS/pod",
            "k8s://prod",
            "s3://-bucket/key",
            "s3://bucket/--recursive",
            "cw://-group::stream",
            "cw://group::-stream",
            "cw://onlygroup",
        ],
    )
    def test_rejects_unsafe_or_malformed_identifiers(self, source):
        with patch("opspilot.proc.subprocess.Popen") as popen:
            with pytest.raises(LogSourceError):
                auto_detect_and_fetch(source)
            popen.assert_not_called()

    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            (
                "/aws/lambda/fn::2026/01/01/[$LATEST]abc",
                ("/aws/lambda/fn", "2026/01/01/[$LATEST]abc"),
            ),
            ("app-group/stream-1", ("app-group", "stream-1")),
        ],
    )
    def test_cloudwatch_parsing(self, spec, expected):
        assert parse_cloudwatch_source(spec) == expected


class TestCliSources:
    def _fake_popen(self, stdout=b"", stderr=b"", returncode=0):
        process = Mock()
        process.stdout.read = Mock(side_effect=[stdout, b""])
        process.stderr.read = Mock(side_effect=[stderr, b""])
        process.returncode = returncode
        process.wait = Mock(return_value=returncode)
        return process

    def test_kubectl_command_uses_separator_before_pod(self):
        with patch("opspilot.proc.subprocess.Popen") as popen:
            popen.return_value = self._fake_popen(stdout=b"pod logs")
            assert auto_detect_and_fetch("k8s://prod/api-7d9f/web") == "pod logs"
            cmd = popen.call_args.args[0]
        assert cmd[:2] == ["kubectl", "logs"]
        assert cmd[-2:] == ["--", "api-7d9f"]
        assert cmd[cmd.index("-c") : cmd.index("-c") + 2] == ["-c", "web"]

    def test_s3_command(self):
        with patch("opspilot.proc.subprocess.Popen") as popen:
            popen.return_value = self._fake_popen(stdout=b"s3 logs")
            assert auto_detect_and_fetch("s3://my-bucket/logs/app.log") == "s3 logs"
            assert popen.call_args.args[0] == [
                "aws",
                "s3",
                "cp",
                "s3://my-bucket/logs/app.log",
                "-",
            ]

    def test_cloudwatch_command_binds_values_to_flags(self):
        with patch("opspilot.proc.subprocess.Popen") as popen:
            popen.return_value = self._fake_popen(stdout=b"cw logs")
            auto_detect_and_fetch("cw:///aws/lambda/fn::stream-1")
            cmd = popen.call_args.args[0]
        assert "--log-group-name=/aws/lambda/fn" in cmd
        assert "--log-stream-name=stream-1" in cmd

    def test_cli_failure_reports_stderr(self):
        with patch("opspilot.proc.subprocess.Popen") as popen:
            popen.return_value = self._fake_popen(stderr=b"AccessDenied", returncode=1)
            with pytest.raises(LogSourceError, match="AccessDenied"):
                auto_detect_and_fetch("s3://my-bucket/app.log")

    def test_missing_cli_reports_install_hint(self):
        with patch(
            "opspilot.proc.subprocess.Popen",
            side_effect=FileNotFoundError,
        ):
            with pytest.raises(LogSourceError, match="install it from"):
                auto_detect_and_fetch("k8s://prod/api")

    def test_real_subprocess_output_is_tail_bounded(self, monkeypatch):
        monkeypatch.setattr(pl, "MAX_FETCH_BYTES", 16)
        code = "import sys; sys.stdout.write('x' * 100000 + 'END-OF-OUTPUT')"
        out = pl._run_cli([sys.executable, "-c", code], "python", "")
        assert out.endswith("END-OF-OUTPUT") and len(out) <= 16

    def test_timeout(self, monkeypatch):
        monkeypatch.setattr(pl, "CLI_TIMEOUT", 0.5)
        code = "import time; time.sleep(30)"
        with pytest.raises(LogSourceError, match="timed out"):
            pl._run_cli([sys.executable, "-c", code], "python", "")


def test_subprocess_module_is_not_shell_based():
    # Guard: no shell=True anywhere in the fetcher.
    import inspect

    assert "shell=True" not in inspect.getsource(pl)
    assert "shell=True" not in inspect.getsource(proc)
    assert subprocess  # imported for clarity
