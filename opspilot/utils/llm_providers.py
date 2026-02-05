"""Multi-provider LLM system with automatic fallback, retry, and circuit breaker.

Supports:
- Ollama (local, free)
- OpenRouter (cloud, free tier)
- Anthropic Claude (cloud, paid)
- Google Gemini (cloud, free tier)
- HuggingFace (cloud, free tier)
"""

import json
import os
import subprocess
import shutil
import time
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import requests

from opspilot.constants import (
    LLM_TIMEOUT,
    LLM_MAX_RETRIES,
    LLM_RETRY_DELAY,
    LLM_RETRY_MULTIPLIER,
    CIRCUIT_BREAKER_THRESHOLD,
    CIRCUIT_BREAKER_TIMEOUT,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    OLLAMA_SUBPROCESS_TIMEOUT,
    DEFAULT_MODELS,
)
from opspilot.exceptions import (
    LLMError,
    LLMTimeoutError,
    LLMResponseError,
    LLMRateLimitError,
    LLMParseError,
)


@dataclass
class CircuitBreaker:
    """Circuit breaker for provider failure protection."""
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    is_open: bool = False

    def record_failure(self):
        """Record a failure and potentially open the circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= CIRCUIT_BREAKER_THRESHOLD:
            self.is_open = True

    def record_success(self):
        """Record success and reset the circuit."""
        self.failure_count = 0
        self.is_open = False
        self.last_failure_time = None

    def can_attempt(self) -> bool:
        """Check if we can attempt a call (circuit is closed or timeout elapsed)."""
        if not self.is_open:
            return True

        # Check if enough time has passed to try again
        if self.last_failure_time:
            elapsed = datetime.now() - self.last_failure_time
            if elapsed > timedelta(seconds=CIRCUIT_BREAKER_TIMEOUT):
                # Half-open state: allow one attempt
                return True

        return False

    def reset(self):
        """Reset the circuit breaker."""
        self.failure_count = 0
        self.is_open = False
        self.last_failure_time = None


@dataclass
class ProviderStats:
    """Statistics for a provider."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls


class LLMProvider:
    """Base class for LLM providers with retry support."""

    def __init__(self, timeout: int = LLM_TIMEOUT):
        self.timeout = timeout
        self.stats = ProviderStats()

    def is_available(self) -> bool:
        """Check if provider is available."""
        raise NotImplementedError

    def call(self, prompt: str) -> str:
        """Call the LLM with a prompt."""
        raise NotImplementedError

    def call_with_retry(
        self,
        prompt: str,
        max_retries: int = LLM_MAX_RETRIES,
        initial_delay: float = LLM_RETRY_DELAY,
    ) -> str:
        """
        Call the LLM with automatic retry and exponential backoff.

        Args:
            prompt: The prompt to send
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay between retries in seconds

        Returns:
            LLM response text

        Raises:
            LLMError: If all retries fail
        """
        # Check circuit breaker
        if not self.stats.circuit_breaker.can_attempt():
            raise LLMError(
                f"{self.__class__.__name__} circuit breaker is open",
                "Too many recent failures, waiting for cooldown"
            )

        last_error = None
        delay = initial_delay

        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                result = self.call(prompt)
                elapsed_ms = (time.time() - start_time) * 1000

                # Record success
                self.stats.total_calls += 1
                self.stats.successful_calls += 1
                self.stats.total_latency_ms += elapsed_ms
                self.stats.circuit_breaker.record_success()

                return result

            except Exception as e:
                last_error = e
                self.stats.total_calls += 1
                self.stats.failed_calls += 1
                self.stats.circuit_breaker.record_failure()

                # Check if it's a rate limit error - don't retry immediately
                if "rate limit" in str(e).lower() or "429" in str(e):
                    raise LLMRateLimitError(self.__class__.__name__)

                # If we have retries left, wait and try again
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= LLM_RETRY_MULTIPLIER

        # All retries exhausted
        raise LLMError(
            f"{self.__class__.__name__} failed after {max_retries + 1} attempts",
            str(last_error)
        )

    def parse_json(self, raw: str) -> Dict:
        """Parse JSON from LLM output."""
        # Try parsing as-is first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from text (handle markdown code blocks)
        content = raw

        # Remove markdown code blocks
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()

        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()

        # Try parsing cleaned content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON object
        start_idx = raw.find('{')
        end_idx = raw.rfind('}')

        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            json_str = raw[start_idx:end_idx + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        raise LLMParseError(raw)


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, model: str = None, timeout: int = LLM_TIMEOUT):
        super().__init__(timeout)
        self.model = model or DEFAULT_MODELS.get("ollama", "llama3")

    def _resolve_ollama_path(self) -> Optional[str]:
        """Resolve Ollama binary path."""
        ollama_path = shutil.which("ollama")
        if ollama_path:
            return ollama_path

        # Windows fallback
        fallback = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
        if fallback.exists():
            return str(fallback)

        return None

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            ollama_path = self._resolve_ollama_path()
            if not ollama_path:
                return False

            result = subprocess.run(
                [ollama_path, "list"],
                capture_output=True,
                timeout=OLLAMA_SUBPROCESS_TIMEOUT,
                check=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def call(self, prompt: str) -> str:
        """Call Ollama LLM."""
        ollama_path = self._resolve_ollama_path()
        if not ollama_path:
            raise LLMError("Ollama not found", "Binary not in PATH or default location")

        try:
            process = subprocess.run(
                [ollama_path, "run", self.model],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout
            )

            if process.returncode != 0:
                raise LLMResponseError("Ollama", process.stderr.strip())

            return process.stdout.strip()

        except subprocess.TimeoutExpired:
            raise LLMTimeoutError("Ollama", self.timeout)


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider - access to many free open-source models."""

    def __init__(self, model: str = None, timeout: int = LLM_TIMEOUT):
        super().__init__(timeout)
        self.model = model or DEFAULT_MODELS.get("openrouter", "openrouter/free")
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def is_available(self) -> bool:
        """Check if OpenRouter API key is configured."""
        return self.api_key is not None and len(self.api_key) > 0

    def call(self, prompt: str) -> str:
        """Call OpenRouter API with free models."""
        if not self.api_key:
            raise LLMError("OpenRouter API key not set", "Set OPENROUTER_API_KEY environment variable")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/opspilot",
            "X-Title": "OpsPilot"
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 429:
                raise LLMRateLimitError("OpenRouter")

            if not response.ok:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                except Exception:
                    error_msg = response.text or f"HTTP {response.status_code}"
                raise LLMResponseError("OpenRouter", error_msg)

            data = response.json()
            return data["choices"][0]["message"]["content"]

        except requests.Timeout:
            raise LLMTimeoutError("OpenRouter", self.timeout)
        except requests.RequestException as e:
            raise LLMError("OpenRouter API call failed", str(e))


class HuggingFaceProvider(LLMProvider):
    """HuggingFace Inference API provider - free tier for open models."""

    def __init__(self, model: str = None, timeout: int = LLM_TIMEOUT):
        super().__init__(timeout)
        self.model = model or DEFAULT_MODELS.get("huggingface", "mistralai/Mistral-7B-Instruct-v0.2")
        self.api_key = os.getenv("HUGGINGFACE_API_KEY")
        self.base_url = f"https://api-inference.huggingface.co/models/{self.model}"

    def is_available(self) -> bool:
        """Check if HuggingFace API key is configured."""
        return self.api_key is not None and len(self.api_key) > 0

    def call(self, prompt: str) -> str:
        """Call HuggingFace Inference API."""
        if not self.api_key:
            raise LLMError("HuggingFace API key not set", "Set HUGGINGFACE_API_KEY environment variable")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": LLM_TEMPERATURE,
                "max_new_tokens": LLM_MAX_TOKENS,
                "return_full_text": False
            }
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 429:
                raise LLMRateLimitError("HuggingFace")

            response.raise_for_status()

            data = response.json()
            if isinstance(data, list):
                return data[0]["generated_text"]
            elif isinstance(data, dict) and "generated_text" in data:
                return data["generated_text"]
            else:
                return str(data)

        except requests.Timeout:
            raise LLMTimeoutError("HuggingFace", self.timeout)
        except requests.RequestException as e:
            raise LLMError("HuggingFace API call failed", str(e))


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str = None, timeout: int = LLM_TIMEOUT):
        super().__init__(timeout)
        self.model = model or DEFAULT_MODELS.get("anthropic", "claude-3-5-haiku-20241022")
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1/messages"

    def is_available(self) -> bool:
        """Check if Anthropic API key is configured."""
        return self.api_key is not None and len(self.api_key) > 0

    def call(self, prompt: str) -> str:
        """Call Anthropic API."""
        if not self.api_key:
            raise LLMError("Anthropic API key not set", "Set ANTHROPIC_API_KEY environment variable")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "max_tokens": LLM_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 429:
                raise LLMRateLimitError("Anthropic")

            response.raise_for_status()

            data = response.json()
            return data["content"][0]["text"]

        except requests.Timeout:
            raise LLMTimeoutError("Anthropic", self.timeout)
        except requests.RequestException as e:
            raise LLMError("Anthropic API call failed", str(e))


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(self, model: str = None, timeout: int = LLM_TIMEOUT):
        super().__init__(timeout)
        self.model = model or DEFAULT_MODELS.get("gemini", "gemini-2.0-flash")
        self.api_key = os.getenv("GOOGLE_API_KEY")

    def is_available(self) -> bool:
        """Check if Google API key is configured."""
        return self.api_key is not None and len(self.api_key) > 0

    def call(self, prompt: str) -> str:
        """Call Google Gemini API."""
        if not self.api_key:
            raise LLMError("Google API key not set", "Set GOOGLE_API_KEY environment variable")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": LLM_TEMPERATURE,
                "maxOutputTokens": LLM_MAX_TOKENS
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)

            if response.status_code == 429:
                raise LLMRateLimitError("Gemini")

            if not response.ok:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                except Exception:
                    error_msg = response.text or f"HTTP {response.status_code}"
                raise LLMResponseError("Gemini", error_msg)

            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        except requests.Timeout:
            raise LLMTimeoutError("Gemini", self.timeout)
        except requests.RequestException as e:
            raise LLMError("Gemini API call failed", str(e))


class LLMRouter:
    """Smart LLM router with automatic fallback, retry, and circuit breaker."""

    def __init__(self, prefer_local: bool = True):
        """
        Initialize LLM router.

        Args:
            prefer_local: If True, try Ollama first (free, local)
        """
        self.prefer_local = prefer_local
        self.providers = self._initialize_providers()
        self.last_successful_provider: Optional[LLMProvider] = None

    def _initialize_providers(self) -> List[LLMProvider]:
        """Initialize providers in priority order (all free/open-source)."""
        if self.prefer_local:
            return [
                OllamaProvider(),
                GeminiProvider(),
                OpenRouterProvider(),
                HuggingFaceProvider()
            ]
        else:
            return [
                GeminiProvider(),
                OpenRouterProvider(),
                HuggingFaceProvider(),
                OllamaProvider()
            ]

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        available = []
        for provider in self.providers:
            if provider.is_available() and provider.stats.circuit_breaker.can_attempt():
                available.append(provider.__class__.__name__)
        return available

    def get_provider_stats(self) -> Dict[str, Dict]:
        """Get statistics for all providers."""
        stats = {}
        for provider in self.providers:
            name = provider.__class__.__name__
            stats[name] = {
                "available": provider.is_available(),
                "total_calls": provider.stats.total_calls,
                "success_rate": provider.stats.success_rate,
                "avg_latency_ms": provider.stats.avg_latency_ms,
                "circuit_open": provider.stats.circuit_breaker.is_open,
            }
        return stats

    def call(self, prompt: str, timeout: int = LLM_TIMEOUT) -> str:
        """
        Call LLM with automatic fallback and retry.

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            LLM response text

        Raises:
            LLMError: If all providers fail
        """
        errors = []

        # Try last successful provider first (if circuit is healthy)
        if self.last_successful_provider:
            if self.last_successful_provider.stats.circuit_breaker.can_attempt():
                try:
                    self.last_successful_provider.timeout = timeout
                    result = self.last_successful_provider.call_with_retry(prompt)
                    return result
                except Exception as e:
                    errors.append(f"{self.last_successful_provider.__class__.__name__}: {e}")

        # Try all providers
        for provider in self.providers:
            if not provider.is_available():
                errors.append(f"{provider.__class__.__name__}: Not available")
                continue

            if not provider.stats.circuit_breaker.can_attempt():
                errors.append(f"{provider.__class__.__name__}: Circuit breaker open")
                continue

            try:
                provider.timeout = timeout
                result = provider.call_with_retry(prompt)

                # Success! Remember this provider
                self.last_successful_provider = provider
                print(f"[LLM] Using {provider.__class__.__name__}")
                return result

            except LLMRateLimitError as e:
                errors.append(f"{provider.__class__.__name__}: Rate limited")
                continue
            except Exception as e:
                errors.append(f"{provider.__class__.__name__}: {e}")
                continue

        # All providers failed
        error_summary = "\n".join(errors)
        raise LLMError(
            "All LLM providers failed",
            f"{error_summary}\n\n"
            f"Setup instructions (all FREE/open-source):\n"
            f"1. Ollama (local): Install from https://ollama.ai/ → ollama pull llama3\n"
            f"2. Google Gemini (free tier): Get key at https://aistudio.google.com/ → export GOOGLE_API_KEY=...\n"
            f"3. OpenRouter (free models): Get key at https://openrouter.ai/ → export OPENROUTER_API_KEY=...\n"
            f"4. HuggingFace (free tier): Get key at https://huggingface.co/settings/tokens → export HUGGINGFACE_API_KEY=..."
        )

    def safe_json_parse(self, raw: str, retry_timeout: int = 15) -> Dict:
        """
        Parse JSON from LLM output with retry.

        Args:
            raw: Raw LLM output
            retry_timeout: Timeout for retry call

        Returns:
            Parsed JSON dict
        """
        # Try parsing with base provider logic
        try:
            provider = self.last_successful_provider or self.providers[0]
            return provider.parse_json(raw)
        except (json.JSONDecodeError, LLMParseError):
            pass

        # Last resort: ask LLM to fix it
        correction_prompt = f"""
The following output was NOT valid JSON.

Return ONLY valid JSON.
No explanation.
No markdown.

INVALID OUTPUT:
{raw}
"""

        try:
            corrected = self.call(correction_prompt, timeout=retry_timeout)
            provider = self.last_successful_provider or self.providers[0]
            return provider.parse_json(corrected)
        except Exception:
            raise LLMParseError(raw)


# Global router instance
_global_router: Optional[LLMRouter] = None


def get_llm_router(prefer_local: bool = True) -> LLMRouter:
    """Get global LLM router instance."""
    global _global_router
    if _global_router is None:
        _global_router = LLMRouter(prefer_local=prefer_local)
    return _global_router


def reset_llm_router():
    """Reset the global LLM router (useful for testing)."""
    global _global_router
    _global_router = None


def call_llama(prompt: str, timeout: int = LLM_TIMEOUT) -> str:
    """
    Call LLM with automatic fallback (backward compatible).

    This function maintains backward compatibility with existing code.
    """
    router = get_llm_router()
    return router.call(prompt, timeout)


def safe_json_parse(raw: str, retry_timeout: int = 15) -> Dict:
    """
    Parse JSON from LLM output (backward compatible).
    """
    router = get_llm_router()
    return router.safe_json_parse(raw, retry_timeout)


def check_ollama_available() -> bool:
    """Check if Ollama is available (backward compatible)."""
    provider = OllamaProvider()
    return provider.is_available()


def check_any_llm_available() -> bool:
    """Check if ANY LLM provider is available."""
    router = get_llm_router()
    return len(router.get_available_providers()) > 0
