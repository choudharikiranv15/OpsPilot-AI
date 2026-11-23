"""Shared fixtures for OpsPilot tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
CANARY = "canary-7f3a9c-not-a-real-secret"


@pytest.fixture
def sample_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the sample project as the working directory, with an isolated home."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURES / "sample_project", project)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(
        "opspilot.memory.MEMORY_FILE", home / ".opspilot_memory.json", raising=False
    )
    monkeypatch.chdir(project)
    return project


def assert_no_canary(*texts: str) -> None:
    for text in texts:
        assert CANARY not in text, "secret canary value leaked into output"
