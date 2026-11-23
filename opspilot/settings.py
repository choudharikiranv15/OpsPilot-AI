"""OpsPilot configuration (single source of truth).

Settings are read, in order of precedence, from:

1. Command-line flags (applied by the CLI as overrides)
2. Environment variables (``OPSPILOT_*``; provider API keys also accept their
   conventional names such as ``GOOGLE_API_KEY``)
3. The user config file: ``$OPSPILOT_CONFIG_FILE`` or
   ``~/.config/opspilot/config.env`` (dotenv syntax)

OpsPilot deliberately does NOT read the analyzed project's ``.env`` file into
its own configuration or process environment: a repository you are debugging
must not be able to change where OpsPilot sends data or which proxy/CA it
trusts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["auto", "ollama", "gemini", "openrouter", "anthropic"]
CLOUD_PROVIDERS = ("gemini", "openrouter", "anthropic")


def user_config_file() -> Path:
    """Location of the user-level config file."""
    override = os.environ.get("OPSPILOT_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "opspilot" / "config.env"


class OpsPilotSettings(BaseSettings):
    """All user-configurable settings."""

    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Provider selection
    provider: ProviderName = Field(
        default="auto",
        description=(
            "LLM provider. 'auto' uses local Ollama only, plus cloud providers "
            "with configured keys when allow_cloud is true. Naming a cloud "
            "provider explicitly counts as opting in to it."
        ),
    )
    model: str | None = Field(
        default=None, description="Model override for the selected provider"
    )
    allow_cloud: bool = Field(
        default=False,
        description="Allow 'auto' mode to fall back to cloud providers",
    )

    # Provider details
    ollama_host: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.2")
    gemini_model: str = Field(default="gemini-2.5-flash")
    anthropic_model: str = Field(default="claude-haiku-5-5")
    openrouter_model: str | None = Field(
        default=None,
        description="Required for OpenRouter (no default: free model IDs change often)",
    )

    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPSPILOT_GOOGLE_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"
        ),
    )
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPSPILOT_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"
        ),
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPSPILOT_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"
        ),
    )

    # Limits
    request_timeout: int = Field(
        default=120, ge=1, description="Timeout for a single LLM request (seconds)"
    )
    deadline: int = Field(
        default=300, ge=1, description="Total time budget for one command (seconds)"
    )
    max_retries: int = Field(
        default=2, ge=0, le=5, description="Retries for transient LLM errors"
    )
    build_timeout: int = Field(
        default=300, ge=1, description="Time limit for --build-cmd (seconds)"
    )

    # Privacy
    redact: bool = Field(
        default=True, description="Redact likely secrets before sending to an LLM"
    )

    @property
    def primary_provider(self) -> str:
        """The provider tried first: the explicit one, or Ollama in auto mode."""
        return "ollama" if self.provider == "auto" else self.provider

    def model_for(self, provider: str) -> str | None:
        """Model to use for a provider. ``model`` overrides only the primary one."""
        if self.model and provider == self.primary_provider:
            return self.model
        return {
            "ollama": self.ollama_model,
            "gemini": self.gemini_model,
            "anthropic": self.anthropic_model,
            "openrouter": self.openrouter_model,
        }.get(provider)


def get_settings(**overrides) -> OpsPilotSettings:
    """Load settings from env and the user config file, applying overrides."""
    clean = {k: v for k, v in overrides.items() if v is not None}
    config_file = user_config_file()
    env_file = config_file if config_file.is_file() else None
    return OpsPilotSettings(_env_file=env_file, **clean)
