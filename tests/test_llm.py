"""Tests for LLM providers, routing policy, retries and structured output."""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests
from pydantic import BaseModel

from opspilot.exceptions import (
    DeadlineExceededError,
    LLMParseError,
    LLMProviderUnavailableError,
)
from opspilot.llm import (
    Deadline,
    LLMRouter,
    OllamaProvider,
    complete_structured,
    parse_json_object,
    permitted_provider_names,
)
from opspilot.settings import OpsPilotSettings

PROVIDER_KEY_VARS = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in PROVIDER_KEY_VARS:
        monkeypatch.delenv(var, raising=False)
    for var in list(__import__("os").environ):
        if var.startswith("OPSPILOT_"):
            monkeypatch.delenv(var, raising=False)


def make_settings(**kwargs: Any) -> OpsPilotSettings:
    return OpsPilotSettings(_env_file=None, **kwargs)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    """Records requests; returns queued responses (or raises queued exceptions)."""

    def __init__(self, tags: list[str] | None = None, ollama_up: bool = True):
        self.tags = tags if tags is not None else ["llama3.2:latest"]
        self.ollama_up = ollama_up
        self.posts: list[dict] = []
        self.queue: list[Any] = []

    def get(self, url: str, timeout: float = 0) -> FakeResponse:
        if not self.ollama_up:
            raise requests.ConnectionError("refused")
        return FakeResponse(200, {"models": [{"name": t} for t in self.tags]})

    def post(
        self, url: str, headers=None, json=None, timeout: float = 0
    ) -> FakeResponse:
        self.posts.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def ollama_reply(obj: Any) -> FakeResponse:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return FakeResponse(200, {"response": text})


# --- provider policy ---------------------------------------------------------


def test_auto_mode_is_local_only_even_when_cloud_keys_exist() -> None:
    settings = make_settings(google_api_key="k", anthropic_api_key="k")
    assert permitted_provider_names(settings) == ["ollama"]


def test_auto_mode_with_allow_cloud_adds_only_keyed_providers() -> None:
    settings = make_settings(allow_cloud=True, anthropic_api_key="k")
    assert permitted_provider_names(settings) == ["ollama", "anthropic"]


def test_explicit_provider_is_used_alone() -> None:
    settings = make_settings(provider="gemini", allow_cloud=True, anthropic_api_key="k")
    assert permitted_provider_names(settings) == ["gemini"]


def test_no_cloud_request_when_ollama_down_and_cloud_not_opted_in() -> None:
    session = FakeSession(ollama_up=False)
    router = LLMRouter(
        make_settings(google_api_key="k", openrouter_api_key="k"), session=session
    )
    with pytest.raises(LLMProviderUnavailableError) as exc:
        router.complete("sys", "user")
    assert session.posts == []
    assert "local-only mode" in str(exc.value)


def test_notify_reports_provider_before_sending() -> None:
    session = FakeSession()
    session.queue.append(ollama_reply({"ok": True}))
    seen = []

    def notify(status):
        seen.append((status.name, len(session.posts)))

    router = LLMRouter(make_settings(), session=session, notify=notify)
    router.complete("sys", "user")
    assert seen == [("ollama", 0)]


# --- Ollama ------------------------------------------------------------------


def test_ollama_missing_model_reports_pull_command_without_downloading() -> None:
    session = FakeSession(tags=["qwen2.5:7b"])
    status = OllamaProvider(make_settings(ollama_model="llama3.2"), session).status()
    assert not status.ready
    assert "ollama pull llama3.2" in status.detail
    assert session.posts == []


@pytest.mark.parametrize(
    ("installed", "wanted", "ready"),
    [
        (["llama3.2:latest"], "llama3.2", True),
        (["llama3.2:3b"], "llama3.2", True),
        (["llama3.2:3b"], "llama3.2:1b", False),
        (["llama3:latest"], "llama3.2", False),
    ],
)
def test_ollama_model_matching(installed, wanted, ready) -> None:
    status = OllamaProvider(
        make_settings(ollama_model=wanted), FakeSession(tags=installed)
    ).status()
    assert status.ready is ready


def test_ollama_request_uses_system_prompt_and_json_mode() -> None:
    session = FakeSession()
    session.queue.append(ollama_reply({"a": 1}))
    LLMRouter(make_settings(), session=session).complete("SYSTEM", "USER")
    body = session.posts[0]["json"]
    assert body["system"] == "SYSTEM"
    assert body["prompt"] == "USER"
    assert body["format"] == "json"
    assert body["stream"] is False


# --- cloud providers -----------------------------------------------------------


def test_gemini_request_and_parse() -> None:
    session = FakeSession()
    session.queue.append(
        FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
    )
    router = LLMRouter(
        make_settings(provider="gemini", google_api_key="secret"), session=session
    )
    assert router.complete("S", "U") == "{}"
    sent = session.posts[0]
    assert sent["headers"]["x-goog-api-key"] == "secret"
    assert sent["json"]["systemInstruction"]["parts"][0]["text"] == "S"


def test_anthropic_request_and_parse() -> None:
    session = FakeSession()
    session.queue.append(
        FakeResponse(200, {"content": [{"type": "text", "text": '{"x": 1}'}]})
    )
    router = LLMRouter(
        make_settings(provider="anthropic", anthropic_api_key="secret"), session=session
    )
    assert router.complete("S", "U") == '{"x": 1}'
    sent = session.posts[0]
    assert sent["json"]["system"] == "S"
    assert sent["json"]["model"] == "claude-haiku-5-5"


def test_openrouter_requires_explicit_model() -> None:
    router = LLMRouter(
        make_settings(provider="openrouter", openrouter_api_key="k"),
        session=FakeSession(),
    )
    assert not router.ready()
    assert "OPSPILOT_OPENROUTER_MODEL" in router.statuses()[0].detail


def test_api_keys_are_not_exposed_in_settings_repr() -> None:
    settings = make_settings(google_api_key="super-secret-value")
    assert "super-secret-value" not in repr(settings)


# --- retries and deadline ------------------------------------------------------


def test_transient_error_is_retried_with_backoff() -> None:
    session = FakeSession()
    session.queue += [FakeResponse(503, {"error": "busy"}), ollama_reply({"ok": 1})]
    sleeps: list[float] = []
    router = LLMRouter(make_settings(), session=session, sleep=sleeps.append)
    assert json.loads(router.complete("s", "u")) == {"ok": 1}
    assert sleeps == [1.0]


def test_client_error_is_not_retried() -> None:
    session = FakeSession()
    session.queue += [FakeResponse(401, {"error": {"message": "bad key"}})]
    sleeps: list[float] = []
    router = LLMRouter(make_settings(), session=session, sleep=sleeps.append)
    with pytest.raises(LLMProviderUnavailableError) as exc:
        router.complete("s", "u")
    assert sleeps == []
    assert "bad key" in str(exc.value)


def test_retries_are_bounded() -> None:
    session = FakeSession()
    session.queue += [requests.Timeout()] * 3
    sleeps: list[float] = []
    router = LLMRouter(
        make_settings(max_retries=2), session=session, sleep=sleeps.append
    )
    with pytest.raises(LLMProviderUnavailableError):
        router.complete("s", "u")
    assert len(session.posts) == 3
    assert sleeps == [1.0, 2.0]


def test_deadline_exceeded_stops_requests() -> None:
    now = [0.0]
    deadline = Deadline(10, clock=lambda: now[0])
    now[0] = 11.0
    session = FakeSession()
    router = LLMRouter(make_settings(), session=session, deadline=deadline)
    with pytest.raises(DeadlineExceededError):
        router.complete("s", "u")
    assert session.posts == []


def test_request_timeout_is_capped_by_remaining_deadline() -> None:
    now = [0.0]
    deadline = Deadline(30, clock=lambda: now[0])
    session = FakeSession()
    session.queue.append(ollama_reply({}))
    router = LLMRouter(
        make_settings(request_timeout=120), session=session, deadline=deadline
    )
    router.complete("s", "u")
    assert session.posts[0]["timeout"] == pytest.approx(30)


# --- structured output -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        'Here you go:\n```json\n{"a": 1}\n```',
        'prefix {"a": 1} suffix',
    ],
)
def test_parse_json_object_variants(raw: str) -> None:
    assert parse_json_object(raw) == {"a": 1}


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]"])
def test_parse_json_object_rejects_non_objects(raw: str) -> None:
    with pytest.raises(LLMParseError):
        parse_json_object(raw)


class Answer(BaseModel):
    value: int


def test_complete_structured_repairs_once() -> None:
    session = FakeSession()
    session.queue += [ollama_reply("nonsense"), ollama_reply({"value": 3})]
    router = LLMRouter(make_settings(), session=session)
    assert complete_structured(router, "s", "u", Answer).value == 3
    assert "could not be used" in session.posts[1]["json"]["prompt"]


def test_complete_structured_gives_up_after_one_repair() -> None:
    session = FakeSession()
    session.queue += [ollama_reply({"value": "x"}), ollama_reply({"value": "y"})]
    router = LLMRouter(make_settings(), session=session)
    with pytest.raises(LLMParseError):
        complete_structured(router, "s", "u", Answer)
    assert len(session.posts) == 2


def test_model_override_applies_only_to_primary_provider() -> None:
    settings = make_settings(model="custom", allow_cloud=True)
    assert settings.model_for("ollama") == "custom"
    assert settings.model_for("gemini") == "gemini-2.5-flash"
    explicit = make_settings(provider="anthropic", model="custom")
    assert explicit.model_for("anthropic") == "custom"
    assert explicit.model_for("ollama") == "llama3.2"
