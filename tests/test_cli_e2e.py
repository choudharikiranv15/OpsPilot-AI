"""End-to-end CLI tests with a fake LLM provider (no network, no Ollama)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from opspilot.cli import app
from tests.conftest import CANARY, assert_no_canary
from tests.test_llm import PROVIDER_KEY_VARS, FakeSession, ollama_reply

APP_MAIN = (
    "import os\n"
    "\n"
    "import redis\n"
    "\n"
    'cache = redis.Redis.from_url(os.environ["REDIS_URL"])\n'
    'DATABASE_URL = os.getenv("DATABASE_URL")\n'
    "\n"
    "\n"
    "def handler(key):\n"
    "    order = cache.get(key)\n"
    "    return order\n"
)
VALID_DIFF = (
    "--- a/app/main.py\n"
    "+++ b/app/main.py\n"
    "@@ -5 +5 @@\n"
    '-cache = redis.Redis.from_url(os.environ["REDIS_URL"])\n'
    '+cache = redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=5)\n'
)


@pytest.fixture
def project(sample_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Normalise line endings so patch checks behave the same on every OS.
    (sample_project / "app" / "main.py").write_bytes(APP_MAIN.encode())
    for var in PROVIDER_KEY_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPSPILOT_CONFIG_FILE", str(sample_project / "no-config.env"))
    return sample_project


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    session = FakeSession()
    monkeypatch.setattr("opspilot.llm.make_session", lambda: session)
    return session


def diagnosis_reply(**overrides) -> dict:
    reply = {
        "summary": "Redis calls time out.",
        "hypotheses": [
            {
                "cause": "Redis is unreachable or too slow, causing socket timeouts",
                "category": "database",
                "confidence": 0.8,
                "evidence": ["F1", "F3", "F99"],
            },
            {
                "cause": "Made-up cause with no evidence",
                "category": "other",
                "confidence": 0.9,
                "evidence": [],
            },
        ],
        "missing_information": ["Redis server metrics"],
        "next_steps": ["Run: redis-cli -u $REDIS_URL ping"],
    }
    reply.update(overrides)
    return reply


def run(*args: str, **kwargs):
    return CliRunner().invoke(app, list(args), **kwargs)


def prompts(session: FakeSession) -> list[str]:
    return [p["json"]["system"] + p["json"]["prompt"] for p in session.posts]


# --- facts only ------------------------------------------------------------------


def test_no_llm_json_is_valid_and_makes_no_llm_calls(project, fake_llm) -> None:
    result = run("analyze", "--no-llm", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["schema_version"] == "1"
    assert data["mode"] == "facts_only"
    kinds = {f["kind"] for f in data["facts"]}
    assert {"log_error", "stack_frame", "config", "log_summary"} <= kinds
    assert any("DATABASE_URL" in f["text"] for f in data["facts"])
    assert data["diagnosis"] is None
    assert fake_llm.posts == []


def test_deprecated_mode_explain_still_works(project, fake_llm) -> None:
    result = run("analyze", "--mode", "explain", "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["mode"] == "facts_only"


def test_troubleshoot_is_a_deprecated_alias(project, fake_llm) -> None:
    result = run("troubleshoot", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["mode"] == "facts_only"
    assert fake_llm.posts == []


# --- diagnosis --------------------------------------------------------------------


def test_diagnosis_keeps_only_real_citations_and_ranks_supported_first(
    project, fake_llm
) -> None:
    fake_llm.queue += [
        ollama_reply(diagnosis_reply()),
        ollama_reply({"suggestions": []}),
    ]
    result = run("analyze", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    top, second = data["diagnosis"]["hypotheses"]
    assert top["evidence"] == ["F1", "F3"]  # F99 does not exist and is dropped
    assert top["supported"] is True
    assert second["supported"] is False
    assert data["llm"]["provider"] == "ollama"
    assert data["llm"]["location"] == "local"


def test_suggestions_are_limited_to_real_project_files_and_checked(
    project, fake_llm
) -> None:
    fixes = {
        "suggestions": [
            {"file": "app/main.py", "diff": VALID_DIFF, "rationale": "add timeout"},
            {"file": "app/config/redis.py", "diff": "--- a\n+++ b\n", "rationale": "x"},
        ]
    }
    fake_llm.queue += [ollama_reply(diagnosis_reply()), ollama_reply(fixes)]
    result = run("analyze", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [s["file"] for s in data["suggestions"]] == ["app/main.py"]
    expected = "applies" if _git_available() else "not_checked"
    assert data["suggestions"][0]["check"] == expected
    assert any("discarded" in w for w in data["warnings"])
    # Dry run: the project file is unchanged.
    assert (project / "app" / "main.py").read_bytes() == APP_MAIN.encode()


def test_no_fix_skips_patch_generation(project, fake_llm) -> None:
    fake_llm.queue.append(ollama_reply(diagnosis_reply()))
    result = run("analyze", "--json", "--no-fix")
    assert result.exit_code == 0, result.output
    assert len(fake_llm.posts) == 1


def test_unsupported_top_hypothesis_produces_warning_and_no_patches(
    project, fake_llm
) -> None:
    reply = diagnosis_reply(
        hypotheses=[{"cause": "guess", "confidence": 0.9, "evidence": ["F404"]}]
    )
    fake_llm.queue.append(ollama_reply(reply))
    result = run("analyze", "--json")
    data = json.loads(result.stdout)
    assert data["suggestions"] == []
    assert len(fake_llm.posts) == 1
    assert any("treat it as a guess" in w for w in data["warnings"])


def test_no_error_inputs_means_no_llm_call(tmp_path, monkeypatch, fake_llm) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPSPILOT_CONFIG_FILE", str(tmp_path / "none.env"))
    result = run("analyze", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["facts"] == []
    assert fake_llm.posts == []
    assert any("No error output" in w for w in data["warnings"])


# --- privacy and safety --------------------------------------------------------------


def test_secrets_never_reach_prompts_or_reports(project, fake_llm) -> None:
    with (project / "logs" / "app.log").open("a", encoding="utf-8") as log:
        log.write(f"2026-11-20 10:07:00 ERROR auth failed DB_PASSWORD={CANARY}\n")
    fake_llm.queue += [
        ollama_reply(diagnosis_reply()),
        ollama_reply({"suggestions": []}),
    ]
    result = run("analyze", "-o", "report.json")
    assert result.exit_code == 0, result.output
    assert_no_canary(*prompts(fake_llm))
    assert '"redactions": 1' in (project / "report.json").read_text("utf-8")


def test_env_values_never_reach_prompts(project, fake_llm) -> None:
    fake_llm.queue += [
        ollama_reply(diagnosis_reply()),
        ollama_reply({"suggestions": []}),
    ]
    run("analyze", "--no-redact")
    assert_no_canary(*prompts(fake_llm))  # .env values are never collected at all
    assert any("OPSPILOT_TEST_SECRET" in p for p in prompts(fake_llm))  # names are


def test_no_cloud_fallback_without_opt_in(project, monkeypatch) -> None:
    session = FakeSession(ollama_up=False)
    monkeypatch.setattr("opspilot.llm.make_session", lambda: session)
    monkeypatch.setenv("GOOGLE_API_KEY", "a-real-looking-key")
    result = run("analyze")
    assert result.exit_code == 2
    assert session.posts == []
    assert "local-only mode" in result.stderr


def test_explicit_cloud_provider_is_announced_before_sending(
    project, monkeypatch
) -> None:
    session = FakeSession()
    monkeypatch.setattr("opspilot.llm.make_session", lambda: session)
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    gemini = {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps(diagnosis_reply())}]}}
        ]
    }
    from tests.test_llm import FakeResponse

    session.queue += [FakeResponse(200, gemini), FakeResponse(200, gemini)]
    result = run("analyze", "--provider", "gemini", "--no-fix")
    assert result.exit_code == 0, result.output
    assert "Using LLM: gemini" in result.stderr
    assert "cloud" in result.stdout


def test_markup_in_logs_and_model_output_is_printed_literally(
    project, fake_llm
) -> None:
    with (project / "logs" / "app.log").open("a", encoding="utf-8") as log:
        log.write(
            "2026-11-20 10:08:00 ERROR bad tag [/db] and [link=https://x.invalid]y[/link]\n"
        )
    reply = diagnosis_reply(summary="Model says [/bold] [red]oops[/red]")
    fake_llm.queue += [ollama_reply(reply), ollama_reply({"suggestions": []})]
    result = run("analyze")
    assert result.exit_code == 0, result.output
    assert "[/db]" in result.stdout
    assert "[red]oops[/red]" in result.stdout


# --- inputs ------------------------------------------------------------------------------


def test_stdin_input(project, fake_llm) -> None:
    text = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'redis'\n"
    result = run("analyze", "--stdin", "--no-llm", "--json", input=text)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert "stdin" in data["inputs"]
    assert any(
        f["kind"] == "build_error" and "No module named" in f["text"]
        for f in data["facts"]
    )


def test_build_cmd_captures_failing_output(project, fake_llm) -> None:
    (project / "fail.py").write_text(
        "import sys\nprint('TypeError: unsupported operand')\nsys.exit(1)\n",
        encoding="utf-8",
    )
    result = run(
        "analyze", "--build-cmd", f'"{sys.executable}" fail.py', "--no-llm", "--json"
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert any("unsupported operand" in f["text"] for f in data["facts"])


def test_build_cmd_missing_executable(project, fake_llm) -> None:
    result = run("analyze", "--build-cmd", "definitely-not-a-real-cmd-xyz", "--no-llm")
    assert result.exit_code == 1
    assert "Command not found" in result.stderr


def test_only_one_error_input_allowed(project, fake_llm) -> None:
    result = run("analyze", "--error", "x", "--build-cmd", "y", "--no-llm")
    assert result.exit_code == 2


def test_explicit_log_source_file(project, fake_llm) -> None:
    other = project / "service.out"
    other.write_text("ERROR worker crashed: KeyError 'user_id'\n", encoding="utf-8")
    result = run("analyze", "--log-source", str(other), "--no-llm", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert any("worker crashed" in f["text"] for f in data["facts"])
    assert not any(
        "redis" in f["text"].lower() for f in data["facts"] if f["kind"] == "log_error"
    )


def test_bad_log_source_fails_cleanly(project, fake_llm) -> None:
    result = run("analyze", "--log-source", "k8s://prod/--oops", "--no-llm")
    assert result.exit_code == 1
    assert "Log source error" in result.stderr


# --- reports and doctor -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["report.md", "report.json", "report.txt"])
def test_reports_are_written(project, fake_llm, name) -> None:
    fake_llm.queue += [
        ollama_reply(diagnosis_reply()),
        ollama_reply({"suggestions": []}),
    ]
    result = run("analyze", "-o", name)
    assert result.exit_code == 0, result.output
    text = (project / name).read_text("utf-8")
    assert "F1" in text
    assert "Redis is unreachable" in text


def test_doctor_reports_ready_local_provider(project, fake_llm) -> None:
    result = run("doctor")
    assert result.exit_code == 0, result.output
    assert "ollama (llama3, local): ready, will be used" in result.stdout


def test_doctor_fails_when_nothing_is_ready(project, monkeypatch) -> None:
    session = FakeSession(ollama_up=False)
    monkeypatch.setattr("opspilot.llm.make_session", lambda: session)
    result = run("doctor")
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "args", [["--help"], ["analyze", "--help"], ["doctor", "--help"]]
)
def test_help_renders(args) -> None:
    result = run(*args)
    assert result.exit_code == 0, result.output
    assert "Usage" in result.stdout


def test_version() -> None:
    result = run("--version")
    assert result.exit_code == 0
    assert "OpsPilot version" in result.stdout


def _git_available() -> bool:
    import shutil

    return shutil.which("git") is not None


def test_non_applying_patches_are_hidden_unless_verbose(project, fake_llm) -> None:
    bad = {
        "suggestions": [
            {
                "file": "app/main.py",
                "diff": "--- a/app/main.py\n+++ b/app/main.py\n@@ -1 +1 @@\n-nope\n+x\n",
            }
        ]
    }
    fake_llm.queue += [ollama_reply(diagnosis_reply()), ollama_reply(bad)]
    result = run("analyze")
    assert "did not apply to your files and are hidden" in result.stdout
    assert "-nope" not in result.stdout
    fake_llm.queue += [ollama_reply(diagnosis_reply()), ollama_reply(bad)]
    result = run("analyze", "--verbose")
    assert "-nope" in result.stdout


def test_no_ai_disclaimer_without_ai_output(tmp_path, monkeypatch, fake_llm) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPSPILOT_CONFIG_FILE", str(tmp_path / "none.env"))
    result = run("analyze", "-o", "r.md")
    assert result.exit_code == 0, result.output
    assert "AI-generated" not in result.stdout
    assert "AI-generated" not in (tmp_path / "r.md").read_text("utf-8")


def test_doctor_suggests_larger_model_for_small_models(project, fake_llm) -> None:
    fake_llm.tags = ["llama3:latest", "llama3.2:latest"]
    result = run("doctor")  # default llama3 (8B): no tip
    assert result.exit_code == 0, result.output
    assert "small model" not in result.stdout
    result = run("doctor", "--model", "llama3.2")
    assert "small model" in result.stdout
