"""Regression tests: .env values must never reach any output (SEC-01)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from opspilot.cli import app
from opspilot.context.docker import find_docker_files
from opspilot.context.env import read_env_names
from opspilot.pipeline import AnalyzeOptions, run_analysis
from tests.conftest import CANARY, assert_no_canary

runner = CliRunner()


def test_env_reader_returns_names_only(sample_project: Path) -> None:
    names = read_env_names(str(sample_project))
    assert names == ["OPSPILOT_TEST_SECRET", "REDIS_URL"]
    assert_no_canary(repr(names))


def test_docker_reader_returns_file_names_only(sample_project: Path) -> None:
    (sample_project / "Dockerfile").write_text(
        f"FROM python:3.12\nENV TOKEN={CANARY}\n", encoding="utf-8"
    )
    assert find_docker_files(str(sample_project)) == ["Dockerfile"]


def test_collected_context_contains_no_secret_values(sample_project: Path) -> None:
    (sample_project / "Dockerfile").write_text(
        f"ENV TOKEN={CANARY}\n", encoding="utf-8"
    )
    result = run_analysis(AnalyzeOptions(str(sample_project), use_llm=False), None)
    assert_no_canary(result.model_dump_json())


@pytest.mark.parametrize("report", ["report.json", "report.md", "report.txt"])
def test_explain_mode_outputs_and_reports_contain_no_secret_values(
    sample_project: Path, report: str
) -> None:
    result = runner.invoke(
        app, ["analyze", "--mode", "explain", "--json", "-o", report]
    )
    assert result.exit_code == 0, result.output
    assert (sample_project / report).exists()
    assert_no_canary(result.output, (sample_project / report).read_text("utf-8"))
