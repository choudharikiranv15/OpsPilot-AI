"""Tests for prompt redaction."""

from __future__ import annotations

import pytest

from opspilot.llm import LLMRouter
from opspilot.redact import redact
from opspilot.settings import OpsPilotSettings
from tests.test_llm import FakeSession, ollama_reply


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("aws key AKIAIOSFODNN7EXAMPLE used", "AKIAIOSFODNN7EXAMPLE"),
        ("token ghp_" + "a" * 36, "ghp_" + "a" * 36),
        ("OPENAI sk-proj-" + "b" * 40, "sk-proj-" + "b" * 40),
        ("anthropic sk-ant-api03-" + "c" * 40, "sk-ant-api03-" + "c" * 40),
        ("key=AIza" + "d" * 35, "AIza" + "d" * 35),
        ("hf_" + "e" * 34, "hf_" + "e" * 34),
        ("Authorization: Bearer abcdefghijklmnop1234", "abcdefghijklmnop1234"),
        ("postgres://app:hunter2secret@db:5432/orders", "hunter2secret"),
        ("DB_PASSWORD=s3cr3t-value", "s3cr3t-value"),
        ('{"api_key": "zxcvbnm123456"}', "zxcvbnm123456"),
        ("client_secret: 9f8e7d6c5b", "9f8e7d6c5b"),
        ("user alice@example.com logged in", "alice@example.com"),
        (
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.SflKxwRJSMeKKF2QT4fw",
            "eyJhbGciOiJIUzI1NiJ9",
        ),
        (
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
            "MIIEow",
        ),
    ],
)
def test_secrets_are_masked(text: str, secret: str) -> None:
    redacted, count = redact(text)
    assert secret not in redacted
    assert count >= 1


@pytest.mark.parametrize(
    "text",
    [
        "2026-11-20 10:05:12 ERROR redis.exceptions.TimeoutError: Timeout reading",
        'File "app/main.py", line 42, in handler',
        "connection refused to db:5432",
        "GET /api/orders failed with status 503",
        "Set REDIS_URL in the environment",
    ],
)
def test_ordinary_log_lines_are_untouched(text: str) -> None:
    assert redact(text) == (text, 0)


def test_router_redacts_prompts_by_default() -> None:
    session = FakeSession()
    session.queue.append(ollama_reply({}))
    router = LLMRouter(OpsPilotSettings(_env_file=None), session=session)
    router.complete("system", "log: DB_PASSWORD=hunter2hunter2")
    assert "hunter2hunter2" not in session.posts[0]["json"]["prompt"]
    assert router.redaction_count == 1


def test_router_redaction_can_be_disabled() -> None:
    session = FakeSession()
    session.queue.append(ollama_reply({}))
    router = LLMRouter(OpsPilotSettings(_env_file=None, redact=False), session=session)
    router.complete("system", "log: DB_PASSWORD=hunter2hunter2")
    assert "hunter2hunter2" in session.posts[0]["json"]["prompt"]
