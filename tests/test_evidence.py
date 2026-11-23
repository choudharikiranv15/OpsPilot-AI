"""Tests for deterministic fact extraction."""

from __future__ import annotations

from pathlib import Path

from opspilot.agents.planner import build_user_prompt
from opspilot.evidence import build_facts, project_relative


def facts_for(root: Path, **kwargs):
    defaults = {
        "build_output": None,
        "build_source": "build output",
        "logs": None,
        "log_source": None,
        "undefined_env": {},
        "commits": None,
    }
    defaults.update(kwargs)
    return build_facts(str(root), **defaults)


def test_log_errors_are_deduplicated_with_counts_and_timestamps_removed(tmp_path):
    logs = (
        "=== logs/app.log ===\n"
        "2026-11-20 10:00:01 INFO started\n"
        "2026-11-20 10:00:02 ERROR Timeout reading from socket (attempt 1)\n"
        "2026-11-20 10:00:03 ERROR Timeout reading from socket (attempt 2)\n"
        "2026-11-20T10:00:04Z ERROR KeyError: 'user'\n"
    )
    facts = [f for f in facts_for(tmp_path, logs=logs) if f.kind == "log_error"]
    assert [(f.text, f.count, f.source) for f in facts] == [
        ("ERROR Timeout reading from socket (attempt 2)", 2, "logs/app.log"),
        ("ERROR KeyError: 'user'", 1, "logs/app.log"),
    ]


def test_info_lines_are_not_facts(tmp_path):
    facts = facts_for(tmp_path, logs="INFO all good\nDEBUG cache warm\n")
    assert [f for f in facts if f.kind == "log_error"] == []


def test_stack_frames_link_to_project_files(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    logs = (
        "Traceback (most recent call last):\n"
        '  File "/srv/container/app/main.py", line 1, in <module>\n'
        '  File "/usr/lib/python3.12/json/decoder.py", line 9, in decode\n'
        "ValueError: bad\n"
    )
    frames = [f for f in facts_for(tmp_path, logs=logs) if f.kind == "stack_frame"]
    assert frames[0].location == "app/main.py:1"
    assert frames[1].location is None
    assert "outside the project" in frames[1].text


def test_build_output_facts(tmp_path):
    output = "src/app.ts:4:7 - error TS2322: Type 'string' is not assignable to type 'number'.\n"
    facts = facts_for(tmp_path, build_output=output, build_source="stdin")
    assert facts[0].kind == "build_error"
    assert "not assignable" in facts[0].text
    assert facts[0].source == "stdin"


def test_config_and_change_facts(tmp_path):
    facts = facts_for(
        tmp_path,
        undefined_env={"DATABASE_URL": "app/db.py"},
        commits=[
            {
                "hash": "abc1234",
                "date": "2026-11-20 09:55:00 +0000",
                "author": "dev",
                "message": "Bump redis client",
                "files": ["requirements.txt"],
            }
        ],
    )
    assert [f.kind for f in facts] == ["config", "change"]
    assert "DATABASE_URL (app/db.py)" in facts[0].text
    assert "Bump redis client" in facts[1].text


def test_fact_ids_are_sequential_and_text_is_bounded(tmp_path):
    logs = "\n".join(f"ERROR failure number {'x' * 500} {i}" for i in range(3))
    facts = facts_for(tmp_path, logs=logs)
    assert [f.id for f in facts] == [f"F{i + 1}" for i in range(len(facts))]
    assert all(len(f.text) <= 300 for f in facts)


def test_project_relative_rejects_paths_outside_project(tmp_path):
    outside = tmp_path.parent / "elsewhere.py"
    assert project_relative(str(outside), tmp_path) is None
    assert project_relative("../../etc/passwd", tmp_path) is None


def test_prompt_contains_numbered_facts_inside_delimiters(tmp_path):
    facts = facts_for(tmp_path, logs="ERROR boom\n")
    prompt = build_user_prompt(facts, {"dependencies": []})
    assert prompt.startswith("<facts>\nF1 [log_error")
    assert "</facts>" in prompt


def test_fixer_excerpt_survives_stale_line_numbers(tmp_path):
    from opspilot.agents.fixer import _excerpt
    from opspilot.models import Fact

    (tmp_path / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    fact = Fact(
        id="F1", kind="stack_frame", text="x", source="logs", location="a.py:42"
    )
    excerpt = _excerpt(tmp_path, "a.py", [fact])
    assert "1 | one" in excerpt and "2 | two" in excerpt


def test_exception_classes_are_recognised_in_build_output(tmp_path):
    output = (
        "ModuleNotFoundError: No module named 'redis'\n"
        "java.lang.NullPointerException: user is null\n"
    )
    texts = [f.text for f in facts_for(tmp_path, build_output=output)]
    assert "ModuleNotFoundError: No module named 'redis'" in texts
    assert "java.lang.NullPointerException: user is null" in texts


def test_dependency_hypotheses_may_target_the_manifest(tmp_path):
    from opspilot.agents.fixer import target_files
    from opspilot.models import Fact, Hypothesis

    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    frame = Fact(id="F2", kind="stack_frame", text="x", source="s", location="app.py:2")
    dep = Hypothesis(cause="redis missing", category="dependency", evidence=["F2"])
    bug = Hypothesis(cause="typo", category="code_bug", evidence=["F2"])
    assert target_files([frame], dep, str(tmp_path)) == ["requirements.txt", "app.py"]
    assert target_files([frame], bug, str(tmp_path)) == ["app.py"]
