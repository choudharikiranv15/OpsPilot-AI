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
- Base reasoning ONLY on provided context
- If information is missing, say so
- Output STRICT JSON only

CRITICAL: Your response must be ONLY valid JSON with this exact format:
{
  "hypothesis": "...",
  "confidence": 0.0,
  "possible_causes": ["..."],
  "required_checks": ["..."]
}

Do not include any text before the opening { or after the closing }.
"""


# ----------------------------
# Ollama resolution & calling
# ----------------------------

def resolve_ollama_path() -> str:
    ollama_path = shutil.which("ollama")
    if ollama_path:
        return ollama_path

    fallback = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    if fallback.exists():
        return str(fallback)

    raise RuntimeError("Ollama not found. Please install or add to PATH.")


def call_llama(prompt: str, timeout: int = 60) -> str:
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
        raise RuntimeError("LLM inference timed out.")

    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip())

    return process.stdout.strip()


# ----------------------------
# Strict JSON enforcement
# ----------------------------

def safe_json_parse(raw: str) -> Dict:
    """
    Parse JSON strictly.
    If parsing fails, ask the model once to correct itself.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        correction_prompt = f"""
The following output was NOT valid JSON.

Return ONLY valid JSON.
No explanation.
No markdown.

INVALID OUTPUT:
{raw}
"""
        corrected = call_llama(correction_prompt, timeout=15)
        return json.loads(corrected)


# ----------------------------
# Planner
# ----------------------------

def plan(context: Dict) -> Dict:
    """
    Planner agent:
    - Summarizes context
    - Calls LLM exactly once
    - Enforces strict JSON output
    """

    summarized_context = {
        "logs": context.get("logs", "")[:2000] if context.get("logs") else None,
        "env_vars": list(context.get("env", {}).keys()),
        "docker_present": bool(context.get("docker")),
        "dependencies": context.get("dependencies", [])[:20],
        "structure": str(context.get("structure", ""))[:1000],
    }

    user_prompt = f"""
PROJECT CONTEXT:
{json.dumps(summarized_context, indent=2)}

Analyze the context and produce a hypothesis.
"""

    full_prompt = SYSTEM_PROMPT + "\n" + user_prompt

    try:
        raw_output = call_llama(full_prompt)
        result = safe_json_parse(raw_output)

        return {
            "hypothesis": result.get("hypothesis"),
            "confidence": float(result.get("confidence", 0.0)),
            "possible_causes": result.get("possible_causes", []),
            "required_checks": result.get("required_checks", []),
        }

    except Exception:
        # Production-grade failure semantics
        return {
            "hypothesis": None,
            "confidence": 0.0,
            "possible_causes": [],
            "required_checks": [],
        }
