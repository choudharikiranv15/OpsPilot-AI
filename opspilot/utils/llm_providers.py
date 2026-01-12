"""Multi-provider LLM system with automatic fallback.

Supports:
- Ollama (local, free)
- OpenAI (cloud, paid)
- Anthropic Claude (cloud, paid)
- Google Gemini (cloud, free tier)
"""

import json
import os
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional, List
import requests


class LLMProvider:
    """Base class for LLM providers."""

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def is_available(self) -> bool:
        """Check if provider is available."""
        raise NotImplementedError

    def call(self, prompt: str) -> str:
        """Call the LLM with a prompt."""
        raise NotImplementedError

    def parse_json(self, raw: str) -> Dict:
        """Parse JSON from LLM output."""
        # Try parsing as-is first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from text
        start_idx = raw.find('{')
        end_idx = raw.rfind('}')

        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            json_str = raw[start_idx:end_idx + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError(
            f"Could not parse LLM output as JSON",
            raw[:100],
            0
        )


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, model: str = "llama3", timeout: int = 60):
        super().__init__(timeout)
        self.model = model

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
                timeout=5,
                check=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def call(self, prompt: str) -> str:
        """Call Ollama LLM."""
        ollama_path = self._resolve_ollama_path()
        if not ollama_path:
            raise RuntimeError("Ollama not found")

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
                raise RuntimeError(f"Ollama failed: {process.stderr.strip()}")

            return process.stdout.strip()

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Ollama inference timed out after {self.timeout}s")


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider - access to many free open-source models."""

    def __init__(self, model: str = "google/gemini-2.0-flash-exp:free", timeout: int = 60):
        super().__init__(timeout)
        self.model = model
        self.api_key = os.getenv("OPENROUTER_API_KEY")  # Free tier available
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def is_available(self) -> bool:
        """Check if OpenRouter API key is configured."""
        return self.api_key is not None

    def call(self, prompt: str) -> str:
        """Call OpenRouter API with free models."""
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY environment variable not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/opspilot",  # Required by OpenRouter
            "X-Title": "OpsPilot"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]

        except requests.RequestException as e:
            raise RuntimeError(f"OpenRouter API call failed: {e}")


class HuggingFaceProvider(LLMProvider):
    """HuggingFace Inference API provider - free tier for open models."""

    def __init__(self, model: str = "mistralai/Mistral-7B-Instruct-v0.2", timeout: int = 60):
        super().__init__(timeout)
        self.model = model
        self.api_key = os.getenv("HUGGINGFACE_API_KEY")  # Free tier available
        self.base_url = f"https://api-inference.huggingface.co/models/{self.model}"

    def is_available(self) -> bool:
        """Check if HuggingFace API key is configured."""
        return self.api_key is not None

    def call(self, prompt: str) -> str:
        """Call HuggingFace Inference API."""
        if not self.api_key:
            raise RuntimeError("HUGGINGFACE_API_KEY environment variable not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": 0.3,
                "max_new_tokens": 2000,
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
            response.raise_for_status()

            data = response.json()
            # HuggingFace returns different formats
            if isinstance(data, list):
                return data[0]["generated_text"]
            elif isinstance(data, dict) and "generated_text" in data:
                return data["generated_text"]
            else:
                return str(data)

        except requests.RequestException as e:
            raise RuntimeError(f"HuggingFace API call failed: {e}")


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str = "claude-3-5-haiku-20241022", timeout: int = 60):
        super().__init__(timeout)
        self.model = model
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1/messages"

    def is_available(self) -> bool:
        """Check if Anthropic API key is configured."""
        return self.api_key is not None

    def call(self, prompt: str) -> str:
        """Call Anthropic API."""
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "max_tokens": 2000,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            return data["content"][0]["text"]

        except requests.RequestException as e:
            raise RuntimeError(f"Anthropic API call failed: {e}")


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(self, model: str = "gemini-2.0-flash-exp", timeout: int = 60):
        super().__init__(timeout)
        self.model = model
        self.api_key = os.getenv("GOOGLE_API_KEY")

    def is_available(self) -> bool:
        """Check if Google API key is configured."""
        return self.api_key is not None

    def call(self, prompt: str) -> str:
        """Call Google Gemini API."""
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY environment variable not set")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2000
            }
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        except requests.RequestException as e:
            raise RuntimeError(f"Google Gemini API call failed: {e}")


class LLMRouter:
    """Smart LLM router with automatic fallback."""

    def __init__(self, prefer_local: bool = True):
        """
        Initialize LLM router.

        Args:
            prefer_local: If True, try Ollama first (free, local)
        """
        self.prefer_local = prefer_local
        self.providers = self._initialize_providers()
        self.last_successful_provider = None

    def _initialize_providers(self) -> List[LLMProvider]:
        """Initialize providers in priority order (all free/open-source)."""
        if self.prefer_local:
            # Local first, then free cloud providers
            return [
                OllamaProvider(),           # Free, local, private
                GeminiProvider(),           # Free tier (Google)
                OpenRouterProvider(),       # Free models via OpenRouter
                HuggingFaceProvider()       # Free tier (HuggingFace)
            ]
        else:
            # Cloud first (faster), then local
            return [
                GeminiProvider(),           # Free tier, fastest
                OpenRouterProvider(),       # Free models, many options
                HuggingFaceProvider(),      # Free tier, open models
                OllamaProvider()            # Free, local fallback
            ]

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        available = []
        for provider in self.providers:
            if provider.is_available():
                available.append(provider.__class__.__name__)
        return available

    def call(self, prompt: str, timeout: int = 60) -> str:
        """
        Call LLM with automatic fallback.

        Tries providers in order until one succeeds.

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            LLM response text

        Raises:
            RuntimeError: If all providers fail
        """
        errors = []

        # Try last successful provider first (if any)
        if self.last_successful_provider:
            try:
                self.last_successful_provider.timeout = timeout
                result = self.last_successful_provider.call(prompt)
                return result
            except Exception as e:
                errors.append(f"{self.last_successful_provider.__class__.__name__}: {e}")
                # Continue to other providers

        # Try all providers
        for provider in self.providers:
            if not provider.is_available():
                errors.append(f"{provider.__class__.__name__}: Not available")
                continue

            try:
                provider.timeout = timeout
                result = provider.call(prompt)

                # Success! Remember this provider
                self.last_successful_provider = provider
                print(f"[LLM] Using {provider.__class__.__name__}")
                return result

            except Exception as e:
                errors.append(f"{provider.__class__.__name__}: {e}")
                continue

        # All providers failed
        error_summary = "\n".join(errors)
        raise RuntimeError(
            f"All LLM providers failed:\n{error_summary}\n\n"
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
        except json.JSONDecodeError:
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
            raise json.JSONDecodeError(
                f"Could not parse LLM output as JSON",
                raw[:100],
                0
            )


# Global router instance
_global_router = None


def get_llm_router(prefer_local: bool = True) -> LLMRouter:
    """Get global LLM router instance."""
    global _global_router
    if _global_router is None:
        _global_router = LLMRouter(prefer_local=prefer_local)
    return _global_router


def call_llama(prompt: str, timeout: int = 60) -> str:
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
