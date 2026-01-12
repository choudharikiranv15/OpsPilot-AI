"""Unit tests for multi-provider LLM system."""

import pytest
from unittest.mock import patch, Mock
from opspilot.utils.llm_providers import (
    OllamaProvider,
    OpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
    LLMRouter
)


class TestOllamaProvider:
    """Test Ollama provider."""

    @patch('opspilot.utils.llm_providers.subprocess.run')
    def test_availability_check_success(self, mock_run):
        """Test Ollama availability check when available."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        provider = OllamaProvider()
        # Mock path resolution
        with patch.object(provider, '_resolve_ollama_path', return_value='/usr/bin/ollama'):
            assert provider.is_available() is True

    def test_availability_check_failure(self):
        """Test Ollama availability check when not available."""
        provider = OllamaProvider()
        with patch.object(provider, '_resolve_ollama_path', return_value=None):
            assert provider.is_available() is False


class TestOpenAIProvider:
    """Test OpenAI provider."""

    def test_availability_with_api_key(self):
        """Test OpenAI availability with API key."""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            provider = OpenAIProvider()
            assert provider.is_available() is True

    def test_availability_without_api_key(self):
        """Test OpenAI availability without API key."""
        with patch.dict('os.environ', {}, clear=True):
            provider = OpenAIProvider()
            assert provider.is_available() is False

    @patch('opspilot.utils.llm_providers.requests.post')
    def test_call_success(self, mock_post):
        """Test successful OpenAI API call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Test response"}
            }]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            provider = OpenAIProvider()
            result = provider.call("Test prompt")
            assert result == "Test response"


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
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Test response"}]
                }
            }]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            result = provider.call("Test prompt")
            assert result == "Test response"


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
                with patch.object(router.providers[1], 'call', return_value="Success"):
                    result = router.call("Test prompt")
                    assert result == "Success"

    def test_all_providers_fail(self):
        """Test error when all providers fail."""
        router = LLMRouter()

        # Mock all providers to fail
        for provider in router.providers:
            with patch.object(provider, 'is_available', return_value=False):
                pass

        with pytest.raises(RuntimeError) as exc_info:
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
