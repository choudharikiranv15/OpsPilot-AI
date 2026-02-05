"""Custom exceptions for OpsPilot."""


class OpsPilotError(Exception):
    """Base exception for all OpsPilot errors."""

    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


# LLM-related exceptions
class LLMError(OpsPilotError):
    """Base exception for LLM-related errors."""
    pass


class LLMProviderUnavailableError(LLMError):
    """Raised when no LLM provider is available."""

    def __init__(self, providers_tried: list = None):
        self.providers_tried = providers_tried or []
        message = "No LLM provider available"
        details = f"Tried: {', '.join(self.providers_tried)}" if self.providers_tried else None
        super().__init__(message, details)


class LLMTimeoutError(LLMError):
    """Raised when LLM call times out."""

    def __init__(self, provider: str, timeout: int):
        self.provider = provider
        self.timeout = timeout
        super().__init__(
            f"LLM call timed out",
            f"Provider: {provider}, Timeout: {timeout}s"
        )


class LLMResponseError(LLMError):
    """Raised when LLM returns invalid response."""

    def __init__(self, provider: str, reason: str):
        self.provider = provider
        self.reason = reason
        super().__init__(
            f"Invalid LLM response from {provider}",
            reason
        )


class LLMParseError(LLMError):
    """Raised when LLM response cannot be parsed as JSON."""

    def __init__(self, raw_response: str = None):
        self.raw_response = raw_response[:200] if raw_response else None
        super().__init__(
            "Failed to parse LLM response as JSON",
            f"Response preview: {self.raw_response}..." if self.raw_response else None
        )


class LLMRateLimitError(LLMError):
    """Raised when LLM provider rate limits the request."""

    def __init__(self, provider: str, retry_after: int = None):
        self.provider = provider
        self.retry_after = retry_after
        details = f"Retry after {retry_after}s" if retry_after else None
        super().__init__(f"Rate limited by {provider}", details)


# Context collection exceptions
class ContextCollectionError(OpsPilotError):
    """Base exception for context collection errors."""
    pass


class LogFetchError(ContextCollectionError):
    """Raised when log fetching fails."""

    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"Failed to fetch logs from {source}", reason)


class DependencyParseError(ContextCollectionError):
    """Raised when dependency file parsing fails."""

    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Failed to parse dependency file: {file_path}", reason)


class EnvironmentReadError(ContextCollectionError):
    """Raised when environment file reading fails."""

    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Failed to read environment file: {file_path}", reason)


# Analysis exceptions
class AnalysisError(OpsPilotError):
    """Base exception for analysis errors."""
    pass


class InsufficientEvidenceError(AnalysisError):
    """Raised when there's not enough evidence for analysis."""

    def __init__(self, missing_context: list = None):
        self.missing_context = missing_context or []
        message = "Insufficient evidence for analysis"
        details = f"Missing: {', '.join(self.missing_context)}" if self.missing_context else None
        super().__init__(message, details)


class HypothesisGenerationError(AnalysisError):
    """Raised when hypothesis generation fails."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__("Failed to generate hypothesis", reason)


class VerificationError(AnalysisError):
    """Raised when verification fails."""

    def __init__(self, hypothesis: str, reason: str):
        self.hypothesis = hypothesis
        self.reason = reason
        super().__init__(f"Failed to verify hypothesis", reason)


# Configuration exceptions
class ConfigurationError(OpsPilotError):
    """Base exception for configuration errors."""
    pass


class InvalidConfigError(ConfigurationError):
    """Raised when configuration is invalid."""

    def __init__(self, config_file: str, reason: str):
        self.config_file = config_file
        self.reason = reason
        super().__init__(f"Invalid configuration in {config_file}", reason)


class MissingConfigError(ConfigurationError):
    """Raised when required configuration is missing."""

    def __init__(self, config_key: str):
        self.config_key = config_key
        super().__init__(f"Missing required configuration: {config_key}")


# Memory exceptions
class MemoryError(OpsPilotError):
    """Base exception for memory/storage errors."""
    pass


class RedisConnectionError(MemoryError):
    """Raised when Redis connection fails."""

    def __init__(self, host: str, port: int, reason: str):
        self.host = host
        self.port = port
        self.reason = reason
        super().__init__(
            f"Failed to connect to Redis at {host}:{port}",
            reason
        )


class MemoryWriteError(MemoryError):
    """Raised when writing to memory fails."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__("Failed to write to memory", reason)


class MemoryReadError(MemoryError):
    """Raised when reading from memory fails."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__("Failed to read from memory", reason)
