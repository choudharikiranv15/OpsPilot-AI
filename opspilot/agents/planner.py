from typing import Dict
import json
import subprocess
import shutil
from pathlib import Path

SYSTEM_PROMPT = """
You are a senior site reliability engineer.

Your task is to analyze project context and form a hypothesis
about the root cause of runtime issues.

Rules:
- Do NOT suggest fixes
- Do NOT use tools
- Think step-by-step
- Base reasoning ONLY on provided context
- If information is missing, say so
- Output STRICT JSON only

JSON format:
{
  "hypothesis": "...",
  "confidence": 0.0,
  "possible_causes": ["..."],
  "required_checks": ["..."]
}
"""

def resolve_ollama_path() -> str:
    """
    Resolve Ollama binary path in a Windows-safe way.
    """
    # 1️⃣ Try PATH
    ollama_path = shutil.which("ollama")
    if ollama_path:
        return ollama_path

    # 2️⃣ Fallback: common Windows install location
    fallback = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    if fallback.exists():
        return str(fallback)

    raise RuntimeError(
        "Ollama not found. Please install Ollama or add it to PATH."
    )


def call_llama(prompt: str, timeout: int = 30) -> str:
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
        raise RuntimeError(
            "LLM inference timed out. Consider using a smaller model or reducing context."
        )

    if process.returncode != 0:
        raise RuntimeError(f"Ollama failed:\n{process.stderr}")

    return process.stdout.strip()

def plan(context: Dict) -> Dict:
    user_prompt = f"""
PROJECT CONTEXT:
{json.dumps(context, indent=2)}

Analyze the context and produce a hypothesis.
"""

    full_prompt = SYSTEM_PROMPT + "\n" + user_prompt

    try:
        raw_output = call_llama(full_prompt)
        return json.loads(raw_output)
    except Exception as e:
        return {
            "hypothesis": "Unable to form hypothesis",
            "confidence": 0.0,
            "possible_causes": [],
            "required_checks": [],
            "error": str(e)
        }

