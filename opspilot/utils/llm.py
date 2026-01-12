"""LLM utility functions shared across agents."""

import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict


def resolve_ollama_path() -> str:
    """
    Resolve Ollama binary path in a cross-platform way.

    Returns:
        Path to Ollama executable

    Raises:
        RuntimeError: If Ollama not found
    """
    ollama_path = shutil.which("ollama")
    if ollama_path:
        return ollama_path

    # Windows fallback
    fallback = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    if fallback.exists():
        return str(fallback)

    raise RuntimeError(
        "Ollama not found. Please install Ollama or add it to PATH.\n"
        "Download from: https://ollama.ai/"
    )


def call_llama(prompt: str, timeout: int = 60) -> str:
    """
    Call Ollama LLM with a prompt.

    Args:
        prompt: The prompt to send
        timeout: Timeout in seconds (default: 60)

    Returns:
        Raw LLM output as string

    Raises:
        RuntimeError: If Ollama fails or times out
    """
    ollama = resolve_ollama_path()

    try:
        process = subprocess.run(
            [ollama, "run", "llama3"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"LLM inference timed out after {timeout}s")

    if process.returncode != 0:
        raise RuntimeError(f"Ollama failed: {process.stderr.strip()}")

    return process.stdout.strip()


def safe_json_parse(raw: str, retry_timeout: int = 15) -> Dict:
    """
    Parse JSON from LLM output with retry on failure.

    Attempts to extract JSON even if wrapped in text.
    If extraction fails, asks LLM once to correct itself.

    Args:
        raw: Raw LLM output
        retry_timeout: Timeout for retry call (default: 15s)

    Returns:
        Parsed JSON dict

    Raises:
        json.JSONDecodeError: If parsing ultimately fails
    """
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
        corrected = call_llama(correction_prompt, timeout=retry_timeout)
        return json.loads(corrected)
    except Exception:
        raise json.JSONDecodeError(
            f"Could not parse LLM output as JSON",
            raw[:100],
            0
        )


def check_ollama_available() -> bool:
    """
    Check if Ollama is available.

    Returns:
        True if Ollama is accessible, False otherwise
    """
    try:
        resolve_ollama_path()
        subprocess.run(
            [resolve_ollama_path(), "list"],
            capture_output=True,
            timeout=5,
            check=True
        )
        return True
    except Exception:
        return False
