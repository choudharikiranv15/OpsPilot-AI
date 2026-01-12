"""LLM utility functions shared across agents.

This module provides backward-compatible wrappers around the new
multi-provider LLM system with automatic fallback.
"""

# Import from new multi-provider system
from opspilot.utils.llm_providers import (
    call_llama,
    safe_json_parse,
    check_ollama_available,
    check_any_llm_available,
    get_llm_router
)

# Re-export for backward compatibility
__all__ = [
    'call_llama',
    'safe_json_parse',
    'check_ollama_available',
    'check_any_llm_available',
    'get_llm_router'
]
