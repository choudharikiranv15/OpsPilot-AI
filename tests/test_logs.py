"""Tests for local log discovery."""

from __future__ import annotations

import os
import time

from opspilot.context import logs
from opspilot.context.logs import find_log_files, read_logs


def test_only_log_files_are_discovered(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "app.log").write_text("ERROR a\n", encoding="utf-8")
    (tmp_path / "logs" / "app.log.1").write_text("ERROR old\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a log\n", encoding="utf-8")
    (tmp_path / "data.jsonl").write_text("{}\n", encoding="utf-8")
    names = sorted(p.name for p in find_log_files(str(tmp_path)))
    assert names == ["app.log", "app.log.1"]


def test_most_recent_files_first_and_relative_headers(tmp_path):
    (tmp_path / "logs").mkdir()
    old = tmp_path / "old.log"
    new = tmp_path / "logs" / "new.log"
    old.write_text("old line\n", encoding="utf-8")
    new.write_text("new line\n", encoding="utf-8")
    past = time.time() - 3600
    os.utime(old, (past, past))
    text = read_logs(str(tmp_path))
    assert text.index("=== logs/new.log ===") < text.index("=== old.log ===")


def test_reads_tail_of_large_files(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "TAIL_BYTES_PER_FILE", 200)
    big = tmp_path / "big.log"
    big.write_text("".join(f"line {i}\n" for i in range(5000)), encoding="utf-8")
    text = read_logs(str(tmp_path), max_size=10_000)
    assert "line 4999" in text
    assert "line 0\n" not in text
    assert len(text) < 400


def test_no_logs_returns_none(tmp_path):
    assert read_logs(str(tmp_path)) is None
