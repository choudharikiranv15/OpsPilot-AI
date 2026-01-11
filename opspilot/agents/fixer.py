from typing import Dict
import json
import subprocess
import shutil
from pathlib import Path


SYSTEM_PROMPT = """
You are a senior engineer generating SAFE, DRY-RUN fix suggestions.

Rules:
- Output ONLY valid JSON
- Do NOT include explanations outside JSON
- Do NOT apply changes
- Diffs must be strings
- If unsure, return an empty suggestions list

STRICT JSON FORMAT:
{
  "suggestions": [
    {
      "file": "path",
      "diff": "unified diff as a string",
      "rationale": "why this helps"
    }
  ]
}

Return ONLY JSON. No text before or after.
"""


def resolve_ollama_path() -> str:
    path = shutil.which("ollama")
    if path:
        return path

    fallback = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    if fallback.exists():
        return str(fallback)

    raise RuntimeError("Ollama not found.")


def call_llama(prompt: str, timeout: int = 30) -> str:
    ollama = resolve_ollama_path()

    process = subprocess.run(
        [ollama, "run", "llama3"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout
    )

    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip())

    return process.stdout.strip()


def safe_json_parse(raw: str) -> Dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        correction_prompt = f"""
The previous output was INVALID JSON.

Return ONLY valid JSON.
No explanation.
Escape newlines properly.

INVALID OUTPUT:
{raw}
"""
        corrected = call_llama(correction_prompt, timeout=15)
        return json.loads(corrected)


def suggest(hypothesis: str, evidence: Dict) -> Dict:
    prompt = SYSTEM_PROMPT + f"""

HYPOTHESIS:
{hypothesis}

EVIDENCE:
{json.dumps(evidence, indent=2)}
"""

    try:
        raw_output = call_llama(prompt)
        return safe_json_parse(raw_output)
    except Exception:
        # Silent failure: template-based fixes will still apply
        return {"suggestions": []}
