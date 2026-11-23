"""Custom exceptions for OpsPilot."""

from __future__ import annotations


class OpsPilotError(Exception):
    """Base exception for all OpsPilot errors."""

    def __init__(self, message: str, details: str | None = None):
        self.message = message
        self.details = details
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class LLMError(OpsPilotError):
    """Base exception for LLM-related errors.

    ``retryable`` marks transient failures (timeouts, rate limits, 5xx,
    connection errors) that may succeed on retry. Everything else fails fast.
    """

    retryable: bool = False


class LLMConfigError(LLMError):
    """The provider is not usable as configured (missing key, model, or service)."""


class LLMProviderUnavailableError(LLMError):
    """No permitted provider could produce a response."""

    def __init__(self, attempts: list[str] | None = None, hint: str | None = None):
        self.attempts = attempts or []
        lines = [f"  - {a}" for a in self.attempts]
        if hint:
            lines.append(hint)
        super().__init__("No LLM provider could answer", "\n" + "\n".join(lines))


class LLMTimeoutError(LLMError):
    """An LLM request timed out."""

    retryable = True

    def __init__(self, provider: str, timeout: float):
        self.provider = provider
        self.timeout = timeout
        super().__init__(f"{provider} request timed out after {timeout:.0f}s")


class LLMRateLimitError(LLMError):
    """The provider rate-limited the request."""

    retryable = True

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"Rate limited by {provider}")


class LLMResponseError(LLMError):
    """The provider returned an error or an unusable response."""

    def __init__(self, provider: str, reason: str, retryable: bool = False):
        self.provider = provider
        self.reason = reason
        self.retryable = retryable
        super().__init__(f"{provider} error", reason)


class LLMParseError(LLMError):
    """The model's output was not valid JSON of the expected shape."""

    def __init__(self, raw_response: str | None = None, reason: str | None = None):
        self.raw_response = (raw_response or "")[:200]
        detail = reason or (
            f"response began with: {self.raw_response!r}" if self.raw_response else None
        )
        super().__init__("Model returned invalid structured output", detail)


class DeadlineExceededError(LLMError):
    """The overall time budget for the command was used up."""

    def __init__(self, seconds: float):
        super().__init__(
            f"Time budget of {seconds:.0f}s exhausted",
            "raise OPSPILOT_DEADLINE or use a faster model",
        )
