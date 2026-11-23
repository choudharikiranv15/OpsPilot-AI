"""Centralized constants and configuration values for OpsPilot."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Version (single source of truth: [project].version in pyproject.toml)
try:
    VERSION = _pkg_version("opspilot-ai")
except PackageNotFoundError:  # running from a source tree without installation
    VERSION = "0.0.0+unknown"

# Timeouts (in seconds)
LLM_TIMEOUT = 60
LLM_RETRY_TIMEOUT = 15
BUILD_CMD_TIMEOUT = 120
PRODUCTION_LOG_TIMEOUT = 30
OLLAMA_SUBPROCESS_TIMEOUT = 5

# Retry settings
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 1.0  # seconds
LLM_RETRY_MULTIPLIER = 2.0  # exponential backoff multiplier

# Circuit breaker settings
CIRCUIT_BREAKER_THRESHOLD = 5  # failures before opening circuit
CIRCUIT_BREAKER_TIMEOUT = 60  # seconds before trying again

# Truncation limits (in characters) - configurable for large codebases
LOG_TRUNCATE_LIMIT = 10000  # Increased from 5000
BUILD_ERROR_TRUNCATE_LIMIT = 8000  # Increased from 4000
STRUCTURE_TRUNCATE_LIMIT = 2000  # Increased from 1000
DEPENDENCY_LIMIT = 50  # Increased from 20
MAX_FILES_SCAN = 1000  # New: Limit files to scan

# LLM response limits
LLM_MAX_TOKENS = 2000
LLM_TEMPERATURE = 0.3

# Confidence thresholds
CONFIDENCE_THRESHOLD = 0.6
HIGH_CONFIDENCE_THRESHOLD = 0.8

# Severity levels
SEVERITY_P0 = "P0"  # Critical - immediate action required
SEVERITY_P1 = "P1"  # High - urgent attention needed
SEVERITY_P2 = "P2"  # Medium - should be addressed soon
SEVERITY_P3 = "P3"  # Low - minor issue

# Redis settings
REDIS_DEFAULT_HOST = "localhost"
REDIS_DEFAULT_PORT = 6379
REDIS_TTL_DAYS = 7
REDIS_MAX_SIMILAR_ISSUES = 10

# Memory settings
MEMORY_MAX_ENTRIES = 100
MEMORY_SIMILARITY_THRESHOLD = 0.7

# Supported dependency files
DEPENDENCY_FILES = {
    "python": ["requirements.txt", "Pipfile", "pyproject.toml", "setup.py"],
    "node": ["package.json", "package-lock.json", "yarn.lock"],
    "ruby": ["Gemfile", "Gemfile.lock"],
    "go": ["go.mod", "go.sum"],
    "rust": ["Cargo.toml", "Cargo.lock"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "dotnet": ["*.csproj", "packages.config"],
}

# Environment variable names
ENV_VARS = {
    "OPENROUTER_API_KEY": "OpenRouter API key",
    "GOOGLE_API_KEY": "Google Gemini API key",
    "ANTHROPIC_API_KEY": "Anthropic API key",
    "HUGGINGFACE_API_KEY": "HuggingFace API key",
    "REDIS_HOST": "Redis host",
    "REDIS_PORT": "Redis port",
}

# Default LLM models per provider
DEFAULT_MODELS = {
    "ollama": "llama3",
    "openrouter": "openrouter/free",
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-3-5-haiku-20241022",
    "huggingface": "mistralai/Mistral-7B-Instruct-v0.2",
}

# Error patterns for severity classification
CRITICAL_PATTERNS = [
    "OutOfMemoryError",
    "FATAL",
    "CRITICAL",
    "panic:",
    "Segmentation fault",
    "kernel panic",
]

HIGH_PATTERNS = [
    "ERROR",
    "Exception",
    "failed",
    "crash",
    "timeout",
    "connection refused",
]

MEDIUM_PATTERNS = [
    "WARN",
    "WARNING",
    "deprecated",
    "retry",
]

LOW_PATTERNS = [
    "INFO",
    "DEBUG",
    "notice",
]
