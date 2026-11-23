"""LLM providers and routing.

Policy (see docs/privacy.md):

* Local first. With ``provider = auto`` (the default) only local Ollama is
  used. Cloud providers are added only when ``allow_cloud`` is set, and only
  those with credentials. Naming a cloud provider explicitly (``--provider
  gemini``) is an explicit opt-in to that provider alone.
* Fallback never silently crosses from local to cloud.
* Only transient errors (timeouts, rate limits, 5xx, connection failures) are
  retried, and every request is bounded by one overall deadline.
* Ollama is called through its HTTP API. A missing model is reported with the
  ``ollama pull`` command; OpsPilot never downloads models implicitly.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from opspilot.exceptions import (
    DeadlineExceededError,
    LLMConfigError,
    LLMError,
    LLMParseError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from opspilot.redact import redact
from opspilot.settings import CLOUD_PROVIDERS, OpsPilotSettings

log = logging.getLogger("opspilot.llm")

MAX_OUTPUT_TOKENS = 2048
TEMPERATURE = 0.2
PROJECT_URL = "https://github.com/choudharikiranv15/OpsPilot-AI"


class Deadline:
    """Overall time budget for one command."""

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic):
        self.seconds = seconds
        self._clock = clock
        self._end = clock() + seconds

    def remaining(self) -> float:
        return max(0.0, self._end - self._clock())

    def check(self) -> None:
        if self.remaining() <= 0:
            raise DeadlineExceededError(self.seconds)


@dataclass
class ProviderStatus:
    """Whether a provider can be used right now, and why not."""

    name: str
    model: str | None
    is_cloud: bool
    ready: bool
    detail: str

    @property
    def label(self) -> str:
        where = "cloud" if self.is_cloud else "local"
        return f"{self.name} ({self.model or 'no model'}, {where})"


class Provider:
    """Base class for an LLM provider."""

    name = "base"
    is_cloud = True

    def __init__(self, settings: OpsPilotSettings, session: requests.Session):
        self.settings = settings
        self.session = session
        self.model = settings.model_for(self.name)
        self._status: ProviderStatus | None = None

    # -- availability -------------------------------------------------------
    def status(self) -> ProviderStatus:
        if self._status is None:
            ready, detail = self._check()
            self._status = ProviderStatus(
                self.name, self.model, self.is_cloud, ready, detail
            )
        return self._status

    def _check(self) -> tuple[bool, str]:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- completion ---------------------------------------------------------
    def complete(self, system: str, user: str, timeout: float) -> str:
        raise NotImplementedError  # pragma: no cover - abstract

    def _post(
        self, url: str, *, headers: dict[str, str], payload: dict, timeout: float
    ) -> dict[str, Any]:
        try:
            response = self.session.post(
                url, headers=headers, json=payload, timeout=timeout
            )
        except requests.Timeout:
            raise LLMTimeoutError(self.name, timeout) from None
        except requests.ConnectionError as e:
            raise LLMResponseError(
                self.name, f"connection failed: {e.__class__.__name__}", retryable=True
            ) from e
        except requests.RequestException as e:
            raise LLMResponseError(self.name, str(e)) from e

        if response.status_code == 429:
            raise LLMRateLimitError(self.name)
        if response.status_code >= 400:
            raise LLMResponseError(
                self.name,
                f"HTTP {response.status_code}: {_error_message(response)}",
                retryable=response.status_code >= 500,
            )
        try:
            data = response.json()
        except ValueError:
            raise LLMResponseError(self.name, "response was not JSON") from None
        if not isinstance(data, dict):
            raise LLMResponseError(self.name, "unexpected response shape")
        return data


def _error_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return (response.text or "").strip()[:300] or "no details"
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message", err))[:300]
        if err:
            return str(err)[:300]
    return str(data)[:300]


class OllamaProvider(Provider):
    name = "ollama"
    is_cloud = False

    @property
    def host(self) -> str:
        return self.settings.ollama_host.rstrip("/")

    def _check(self) -> tuple[bool, str]:
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=3)
            response.raise_for_status()
            installed = [m.get("name", "") for m in response.json().get("models", [])]
        except (requests.RequestException, ValueError, AttributeError):
            return False, (
                f"Ollama is not reachable at {self.host}. Install it from "
                "https://ollama.com and make sure it is running."
            )
        if not self.model:
            return False, "No Ollama model configured (set OPSPILOT_OLLAMA_MODEL)."
        if not _ollama_has_model(installed, self.model):
            shown = ", ".join(installed) or "none"
            return False, (
                f"Model '{self.model}' is not installed (installed: {shown}). "
                f"Run: ollama pull {self.model}  (or set OPSPILOT_OLLAMA_MODEL)"
            )
        return True, f"running at {self.host}"

    def complete(self, system: str, user: str, timeout: float) -> str:
        data = self._post(
            f"{self.host}/api/generate",
            headers={"Content-Type": "application/json"},
            payload={
                "model": self.model,
                "system": system,
                "prompt": user,
                "stream": False,
                "format": "json",
                "options": {"temperature": TEMPERATURE},
            },
            timeout=timeout,
        )
        text = data.get("response")
        if not isinstance(text, str) or not text.strip():
            raise LLMResponseError(self.name, "empty response")
        return text


def _ollama_has_model(installed: list[str], wanted: str) -> bool:
    for name in installed:
        if name == wanted:
            return True
        if ":" not in wanted and name.split(":", 1)[0] == wanted:
            return True
    return False


class GeminiProvider(Provider):
    name = "gemini"

    def _check(self) -> tuple[bool, str]:
        if not self.settings.google_api_key:
            return False, "GOOGLE_API_KEY is not set."
        return True, "API key configured"

    def complete(self, system: str, user: str, timeout: float) -> str:
        key = self.settings.google_api_key
        if not key:
            raise LLMConfigError("GOOGLE_API_KEY is not set")
        data = self._post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent",
            headers={
                "x-goog-api-key": key.get_secret_value(),
                "Content-Type": "application/json",
            },
            payload={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": TEMPERATURE,
                    "maxOutputTokens": MAX_OUTPUT_TOKENS,
                    "responseMimeType": "application/json",
                },
            },
            timeout=timeout,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            raise LLMResponseError(self.name, "no candidates in response") from None
        if not text.strip():
            raise LLMResponseError(self.name, "empty response")
        return text


class OpenRouterProvider(Provider):
    name = "openrouter"

    def _check(self) -> tuple[bool, str]:
        if not self.settings.openrouter_api_key:
            return False, "OPENROUTER_API_KEY is not set."
        if not self.model:
            return False, (
                "No OpenRouter model configured. Set OPSPILOT_OPENROUTER_MODEL "
                "(see https://openrouter.ai/models)."
            )
        return True, "API key configured"

    def complete(self, system: str, user: str, timeout: float) -> str:
        key = self.settings.openrouter_api_key
        if not key or not self.model:
            raise LLMConfigError("OpenRouter is not configured")
        data = self._post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key.get_secret_value()}",
                "Content-Type": "application/json",
                "HTTP-Referer": PROJECT_URL,
                "X-Title": "OpsPilot",
            },
            payload={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": TEMPERATURE,
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout=timeout,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMResponseError(self.name, "no choices in response") from None
        if not isinstance(text, str) or not text.strip():
            raise LLMResponseError(self.name, "empty response")
        return text


class AnthropicProvider(Provider):
    name = "anthropic"

    def _check(self) -> tuple[bool, str]:
        if not self.settings.anthropic_api_key:
            return False, "ANTHROPIC_API_KEY is not set."
        return True, "API key configured"

    def complete(self, system: str, user: str, timeout: float) -> str:
        key = self.settings.anthropic_api_key
        if not key:
            raise LLMConfigError("ANTHROPIC_API_KEY is not set")
        data = self._post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key.get_secret_value(),
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=timeout,
        )
        blocks = data.get("content") or []
        text = "".join(
            b.get("text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )
        if not text.strip():
            raise LLMResponseError(self.name, "empty response")
        return text


PROVIDERS: dict[str, type[Provider]] = {
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
    "anthropic": AnthropicProvider,
}


def permitted_provider_names(settings: OpsPilotSettings) -> list[str]:
    """Providers OpsPilot may send data to under the current settings."""
    if settings.provider != "auto":
        return [settings.provider]
    names = ["ollama"]
    if settings.allow_cloud:
        keys = {
            "gemini": settings.google_api_key,
            "openrouter": settings.openrouter_api_key,
            "anthropic": settings.anthropic_api_key,
        }
        names += [n for n in CLOUD_PROVIDERS if keys[n]]
    return names


def make_session() -> requests.Session:
    """HTTP session factory (patched in tests)."""
    return requests.Session()


class LLMRouter:
    """Routes completions to permitted providers with bounded retries."""

    def __init__(
        self,
        settings: OpsPilotSettings,
        *,
        deadline: Deadline | None = None,
        session: requests.Session | None = None,
        notify: Callable[[ProviderStatus], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self.deadline = deadline or Deadline(settings.deadline)
        self._session = session or make_session()
        self.providers = [
            PROVIDERS[name](settings, self._session)
            for name in permitted_provider_names(settings)
        ]
        self._notify = notify
        self._sleep = sleep
        self.active: ProviderStatus | None = None
        self.request_count = 0
        self.redaction_count = 0

    def statuses(self) -> list[ProviderStatus]:
        return [p.status() for p in self.providers]

    def ready(self) -> bool:
        return any(s.ready for s in self.statuses())

    def unavailable_hint(self) -> str:
        if self.settings.provider == "auto" and not self.settings.allow_cloud:
            return (
                "OpsPilot runs in local-only mode by default. Start Ollama and "
                "pull the model, or opt in to a cloud provider (for example "
                "--provider gemini). Run 'opspilot doctor' for details."
            )
        return "Run 'opspilot doctor' for details."

    def complete(self, system: str, user: str) -> str:
        """Return raw model text from the first permitted provider that answers.

        The prompt is redacted (see opspilot.redact) before any provider sees it.
        """
        if self.settings.redact:
            user, count = redact(user)
            self.redaction_count += count
        attempts: list[str] = []
        for provider in self.providers:
            status = provider.status()
            if not status.ready:
                attempts.append(f"{status.name}: {status.detail}")
                continue
            if self.active is None or self.active.name != status.name:
                self.active = status
                if self._notify:
                    self._notify(status)
            try:
                return self._complete_with_retries(provider, system, user)
            except DeadlineExceededError:
                raise
            except LLMError as e:
                attempts.append(f"{status.name}: {e}")
                log.debug("provider %s failed: %s", status.name, e)
        raise LLMProviderUnavailableError(attempts, self.unavailable_hint())

    def _complete_with_retries(self, provider: Provider, system: str, user: str) -> str:
        delay = 1.0
        for attempt in range(self.settings.max_retries + 1):
            self.deadline.check()
            timeout = min(
                float(self.settings.request_timeout), self.deadline.remaining()
            )
            started = time.monotonic()
            try:
                self.request_count += 1
                text = provider.complete(system, user, timeout)
                log.debug(
                    "%s answered in %.1fs (prompt %d chars)",
                    provider.name,
                    time.monotonic() - started,
                    len(system) + len(user),
                )
                return text
            except LLMError as e:
                can_retry = (
                    e.retryable
                    and attempt < self.settings.max_retries
                    and self.deadline.remaining() > delay
                )
                if not can_retry:
                    raise
                log.debug("transient error from %s (%s); retrying", provider.name, e)
                self._sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")  # pragma: no cover


def parse_json_object(raw: str) -> dict[str, Any]:
    """Extract a JSON object from model output (tolerates code fences/prose)."""
    text = (raw or "").strip()
    candidates = [text]
    if "```" in text:
        for chunk in text.split("```")[1::2]:
            candidates.append(chunk.removeprefix("json").strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    raise LLMParseError(raw, "no JSON object found")


ModelT = TypeVar("ModelT", bound=BaseModel)


def complete_structured(
    router: LLMRouter, system: str, user: str, schema: type[ModelT]
) -> ModelT:
    """Ask for JSON matching ``schema``; one repair attempt on invalid output."""
    raw = router.complete(system, user)
    try:
        return schema.model_validate(parse_json_object(raw))
    except (LLMParseError, ValidationError) as first_error:
        reason = _short_reason(first_error)
        log.debug("invalid structured output (%s); asking once more", reason)
    repair = (
        f"{user}\n\nYour previous reply could not be used ({reason}). "
        "Reply again with ONLY one JSON object that follows the required format."
    )
    raw = router.complete(system, repair)
    try:
        return schema.model_validate(parse_json_object(raw))
    except (LLMParseError, ValidationError) as e:
        raise LLMParseError(raw, _short_reason(e)) from None


def _short_reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first = error.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        return f"field '{loc}': {first.get('msg')}"
    return str(error)[:200]
