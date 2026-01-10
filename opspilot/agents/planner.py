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
- Output STRICT JSON only - NO explanatory text before or after

CRITICAL: Your response must be ONLY valid JSON with this exact format:
{
  "hypothesis": "...",
  "confidence": 0.0,
  "possible_causes": ["..."],
  "required_checks": ["..."]
}

Do not include any text before the opening { or after the closing }.
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


def call_llama(prompt: str, timeout: int = 120) -> str:
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
            f"LLM inference timed out after {timeout}s. Consider using a smaller model or reducing context."
        )

    if process.returncode != 0:
        raise RuntimeError(f"Ollama failed:\n{process.stderr}")

    return process.stdout.strip()

def plan(context: Dict) -> Dict:
    # Summarize context to reduce token count
    summarized_context = {
        "logs": context.get("logs", "")[:2000] if context.get("logs") else None,  # Limit log size
        "env": list(context.get("env", {}).keys()),  # Only env var names, not values
        "docker": bool(context.get("docker")),
        "dependencies": context.get("dependencies", [])[:20],  # Limit deps
        "structure": str(context.get("structure", ""))[:1000]  # Limit structure
    }

    user_prompt = f"""
PROJECT CONTEXT:
{json.dumps(summarized_context, indent=2)}

Analyze the context and produce a hypothesis.
"""

    full_prompt = SYSTEM_PROMPT + "\n" + user_prompt
    print(f"[DEBUG] Calling LLM with {len(full_prompt)} chars of prompt...")

    try:
        raw_output = call_llama(full_prompt)

        # Try to extract JSON from the output (LLM often adds explanatory text)
        # Look for JSON object between curly braces
        start_idx = raw_output.find('{')
        end_idx = raw_output.rfind('}')

        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            json_str = raw_output[start_idx:end_idx + 1]
            result = json.loads(json_str)
            print(f"[DEBUG] Successfully parsed hypothesis with confidence {result.get('confidence')}")
            return result
        else:
            # If no braces found, try parsing the whole thing
            return json.loads(raw_output)

    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON from LLM: {e}")
        print(f"[ERROR] Raw output was: {raw_output}")
        return {
            "hypothesis": "Unable to form hypothesis",
            "confidence": 0.0,
            "possible_causes": [],
            "required_checks": [],
            "error": f"JSON parsing failed: {str(e)}"
        }
    except Exception as e:
        print(f"[ERROR] Planner failed: {type(e).__name__}: {e}")
        return {
            "hypothesis": "Unable to form hypothesis",
            "confidence": 0.0,
            "possible_causes": [],
            "required_checks": [],
            "error": str(e)
        }

