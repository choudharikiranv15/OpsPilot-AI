"""Modern configuration management with Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpsPilotSettings(BaseSettings):
    """
    OpsPilot configuration with automatic environment variable loading.

    All settings can be overridden via environment variables with OPSPILOT_ prefix.
    Example: OPSPILOT_LLM_TIMEOUT=120
    """

    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Settings
    llm_timeout: int = Field(default=60, description="LLM call timeout in seconds")
    llm_max_retries: int = Field(default=3, description="Maximum LLM retry attempts")
    llm_retry_delay: float = Field(
        default=1.0, description="Initial retry delay in seconds"
    )
    llm_max_tokens: int = Field(
        default=2000, description="Maximum tokens in LLM response"
    )
    llm_temperature: float = Field(default=0.3, description="LLM temperature (0.0-1.0)")
    prefer_local: bool = Field(
        default=True, description="Prefer local LLM (Ollama) over cloud"
    )

    # Provider API Keys (optional)
    openrouter_api_key: str | None = Field(
        default=None, description="OpenRouter API key"
    )
    google_api_key: str | None = Field(
        default=None, description="Google Gemini API key"
    )
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key")
    huggingface_api_key: str | None = Field(
        default=None, description="HuggingFace API key"
    )

    # Model Overrides
    ollama_model: str = Field(default="llama3.2", description="Ollama model name")
    openrouter_model: str = Field(
        default="google/gemini-2.0-flash-exp:free", description="OpenRouter model"
    )
    gemini_model: str = Field(default="gemini-2.0-flash", description="Gemini model")
    anthropic_model: str = Field(
        default="claude-3-5-haiku-20241022", description="Anthropic model"
    )
    huggingface_model: str = Field(
        default="mistralai/Mistral-7B-Instruct-v0.2", description="HuggingFace model"
    )

    # Redis Settings
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: str | None = Field(default=None, description="Redis password")
    redis_ttl_days: int = Field(default=30, description="Redis TTL in days")

    # Analysis Settings
    confidence_threshold: float = Field(
        default=0.6, description="Minimum confidence for fixes", ge=0.0, le=1.0
    )
    max_similar_issues: int = Field(
        default=5, description="Max similar issues to return"
    )

    # Truncation Limits
    log_truncate_limit: int = Field(default=5000, description="Log truncation limit")
    build_error_truncate_limit: int = Field(
        default=4000, description="Build error truncation"
    )

    # Timeouts
    build_cmd_timeout: int = Field(default=120, description="Build command timeout")
    production_log_timeout: int = Field(
        default=30, description="Production log fetch timeout"
    )

    # Circuit Breaker
    circuit_breaker_threshold: int = Field(
        default=5, description="Failures before opening circuit"
    )
    circuit_breaker_timeout: int = Field(
        default=60, description="Seconds before retrying after circuit opens"
    )

    @property
    def has_any_llm_provider(self) -> bool:
        """Check if at least one LLM provider is available."""
        # Check for Ollama (via command)
        import shutil

        if shutil.which("ollama"):
            return True

        # Check for cloud API keys
        return any(
            [
                self.openrouter_api_key,
                self.google_api_key,
                self.anthropic_api_key,
                self.huggingface_api_key,
            ]
        )

    def get_default_models(self) -> dict[str, str]:
        """Get default model mapping for all providers."""
        return {
            "ollama": self.ollama_model,
            "openrouter": self.openrouter_model,
            "gemini": self.gemini_model,
            "anthropic": self.anthropic_model,
            "huggingface": self.huggingface_model,
        }


# Global settings instance
_settings: OpsPilotSettings | None = None


def get_settings() -> OpsPilotSettings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = OpsPilotSettings()
    return _settings


def reset_settings():
    """Reset settings (useful for testing)."""
    global _settings
    _settings = None
