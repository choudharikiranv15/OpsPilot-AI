"""Tests for the local diagnosis history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opspilot import memory

EVIDENCE = {
    "error_patterns": {
        "exceptions": ["TimeoutError"],
        "http_errors": {"503": 2},
        "log_lines": ["secret detail that must not be stored"],
    }
}


@pytest.fixture
def memory_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".opspilot_memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", path)
    return path


def test_save_stores_minimal_fields_only(memory_file: Path) -> None:
    memory.save_memory("/proj", "Redis timeouts", EVIDENCE)
    stored = json.loads(memory_file.read_text("utf-8"))
    assert set(stored[0]) == {
        "project",
        "timestamp",
        "hypothesis",
        "fingerprint",
        "signals",
    }
    assert "secret detail" not in memory_file.read_text("utf-8")


def test_history_is_capped(memory_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory, "MEMORY_MAX_ENTRIES", 3)
    for i in range(5):
        memory.save_memory("/proj", f"h{i}", EVIDENCE)
    hypotheses = [e["hypothesis"] for e in memory.load_memory()]
    assert hypotheses == ["h2", "h3", "h4"]


def test_corrupt_file_is_quarantined_and_run_continues(memory_file: Path) -> None:
    memory_file.write_text("{ not json", encoding="utf-8")
    assert memory.load_memory() == []
    assert not memory_file.exists()
    assert list(memory_file.parent.glob(".opspilot_memory.json.corrupt-*"))
    memory.save_memory("/proj", "works again", EVIDENCE)
    assert memory.load_memory()[0]["hypothesis"] == "works again"


def test_malformed_entries_are_ignored(memory_file: Path) -> None:
    memory_file.write_text(
        json.dumps([{"no_project": 1}, "junk", {"project": "/p", "hypothesis": "ok"}]),
        encoding="utf-8",
    )
    assert [e["hypothesis"] for e in memory.load_memory()] == ["ok"]


def test_similar_issues_match_project_and_fingerprint(memory_file: Path) -> None:
    memory.save_memory("/proj", "redis", EVIDENCE)
    memory.save_memory("/other", "elsewhere", EVIDENCE)
    memory.save_memory(
        "/proj", "different error", {"error_patterns": {"exceptions": ["KeyError"]}}
    )
    similar = memory.find_similar_issues("/proj", EVIDENCE)
    assert [e["hypothesis"] for e in similar] == ["redis"]
    assert len(memory.find_similar_issues("/proj")) == 2


def test_old_entries_with_full_evidence_are_upgraded(memory_file: Path) -> None:
    memory_file.write_text(
        json.dumps([{"project": "/proj", "hypothesis": "old", "evidence": EVIDENCE}]),
        encoding="utf-8",
    )
    assert memory.find_similar_issues("/proj", EVIDENCE)[0]["hypothesis"] == "old"
    memory.save_memory("/proj", "new", EVIDENCE)
    assert "secret detail" not in memory_file.read_text("utf-8")
