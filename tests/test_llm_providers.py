"""Unit tests for multi-provider LLM system."""

import pytest
from unittest.mock import patch, Mock
from opspilot.utils.llm_providers import (
    OllamaProvider,
    OpenRouterProvider,
    AnthropicProvider,
    GeminiProvider,
    HuggingFaceProvider,
    LLMRouter,
    CircuitBreaker,
    ProviderStats,
)
from opspilot.exceptions import LLMError, LLMTimeoutError, LLMRateLimitError


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state(self):
        """Test circuit breaker starts closed."""
        cb = CircuitBreaker()
        assert cb.is_open is False
        assert cb.failure_count == 0
        assert cb.can_attempt() is True

    def test_opens_after_threshold(self):
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker()
        for _ in range(5):  # CIRCUIT_BREAKER_THRESHOLD = 5
            cb.record_failure()
        assert cb.is_open is True
        assert cb.can_attempt() is False

    def test_resets_on_success(self):
        """Test circuit resets on success."""
        cb = CircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.is_open is False
        assert cb.failure_count == 0


class TestOllamaProvider:
    """Test Ollama provider."""

    @patch('opspilot.utils.llm_providers.subprocess.run')
    def test_availability_check_success(self, mock_run):
        """Test Ollama availability check when available."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        provider = OllamaProvider()
        with patch.object(provider, '_resolve_ollama_path', return_value='/usr/bin/ollama'):
            assert provider.is_available() is True

    def test_availability_check_failure(self):
        """Test Ollama availability check when not available."""
        provider = OllamaProvider()
        with patch.object(provider, '_resolve_ollama_path', return_value=None):
            assert provider.is_available() is False


class TestOpenRouterProvider:
    """Test OpenRouter provider."""

    def test_availability_with_api_key(self):
        """Test OpenRouter availability with API key."""
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
            provider = OpenRouterProvider()
            assert provider.is_available() is True

    def test_availability_without_api_key(self):
        """Test OpenRouter availability without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = OpenRouterProvider()
            assert provider.is_available() is False

    @patch('opspilot.utils.llm_providers.requests.post')
    def test_call_success(self, mock_post):
        """Test successful OpenRouter API call."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Test response"}
            }]
        }
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
            provider = OpenRouterProvider()
            result = provider.call("Test prompt")
            assert result == "Test response"

    @patch('opspilot.utils.llm_providers.requests.post')
    def test_rate_limit_error(self, mock_post):
        """Test rate limit error handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
            provider = OpenRouterProvider()
            with pytest.raises(LLMRateLimitError):
                provider.call("Test prompt")


class TestAnthropicProvider:
    """Test Anthropic provider."""

    def test_availability_with_api_key(self):
        """Test Anthropic availability with API key."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            provider = AnthropicProvider()
            assert provider.is_available() is True

    def test_availability_without_api_key(self):
        """Test Anthropic availability without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = AnthropicProvider()
            assert provider.is_available() is False

    @patch('opspilot.utils.llm_providers.requests.post')
    def test_call_success(self, mock_post):
        """Test successful Anthropic API call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "content": [{"text": "Test response"}]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            provider = AnthropicProvider()
            result = provider.call("Test prompt")
            assert result == "Test response"


class TestGeminiProvider:
    """Test Google Gemini provider."""

    def test_availability_with_api_key(self):
        """Test Gemini availability with API key."""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            assert provider.is_available() is True

    def test_availability_without_api_key(self):
        """Test Gemini availability without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = GeminiProvider()
            assert provider.is_available() is False

    @patch('opspilot.utils.llm_providers.requests.post')
    def test_call_success(self, mock_post):
        """Test successful Gemini API call."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Test response"}]
                }
            }]
        }
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            result = provider.call("Test prompt")
            assert result == "Test response"


class TestHuggingFaceProvider:
    """Test HuggingFace provider."""

    def test_availability_with_api_key(self):
        """Test HuggingFace availability with API key."""
        with patch.dict('os.environ', {'HUGGINGFACE_API_KEY': 'test-key'}):
            provider = HuggingFaceProvider()
            assert provider.is_available() is True

    def test_availability_without_api_key(self):
        """Test HuggingFace availability without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = HuggingFaceProvider()
            assert provider.is_available() is False


class TestLLMRouter:
    """Test LLM router with automatic fallback."""

    def test_get_available_providers(self):
        """Test getting list of available providers."""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            router = LLMRouter()
            available = router.get_available_providers()
            assert 'GeminiProvider' in available

    def test_fallback_to_next_provider(self):
        """Test automatic fallback when first provider fails."""
        router = LLMRouter(prefer_local=True)

        # Mock first provider to fail
        with patch.object(router.providers[0], 'is_available', return_value=False):
            # Mock second provider to succeed
            with patch.object(router.providers[1], 'is_available', return_value=True):
                with patch.object(router.providers[1], 'call_with_retry', return_value="Success"):
                    result = router.call("Test prompt")
                    assert result == "Success"

    def test_all_providers_fail(self):
        """Test error when all providers fail."""
        router = LLMRouter()

        # Mock all providers to be unavailable
        for provider in router.providers:
            provider.stats.circuit_breaker.is_open = False

        with patch.object(router.providers[0], 'is_available', return_value=False):
            with patch.object(router.providers[1], 'is_available', return_value=False):
                with patch.object(router.providers[2], 'is_available', return_value=False):
                    with patch.object(router.providers[3], 'is_available', return_value=False):
                        with pytest.raises(LLMError) as exc_info:
                            router.call("Test prompt")
                        assert "All LLM providers failed" in str(exc_info.value)

    def test_json_parsing(self):
        """Test JSON parsing from LLM output."""
        router = LLMRouter()

        # Test plain JSON
        result = router.safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

        # Test JSON wrapped in text
        wrapped = 'Here is the JSON:\n{"key": "value"}\nEnd of JSON'
        result = router.safe_json_parse(wrapped)
        assert result == {"key": "value"}

    def test_json_parsing_markdown(self):
        """Test JSON parsing from markdown code blocks."""
        router = LLMRouter()

        # Test JSON in markdown code block
        markdown = '```json\n{"key": "value"}\n```'
        result = router.safe_json_parse(markdown)
        assert result == {"key": "value"}

    def test_provider_stats(self):
        """Test provider statistics."""
        router = LLMRouter()
        stats = router.get_provider_stats()

        assert 'OllamaProvider' in stats
        assert 'GeminiProvider' in stats
        assert 'success_rate' in stats['OllamaProvider']
        assert 'circuit_open' in stats['OllamaProvider']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
