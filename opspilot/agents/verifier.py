from typing import Dict
import json
import subprocess
import shutil
from pathlib import Path

SYSTEM_PROMPT = """
You are a senior reliability engineer.

You are given:
- A hypothesis
- Evidence collected from tools

Your task:
- Decide if the hypothesis is supported
- Explain briefly
- Update confidence
- Output STRICT JSON only

Format:
{
  "supported": true/false,
  "confidence": 0.0,
  "reason": "..."
}
"""


def resolve_ollama_path() -> str:
    path = shutil.which("ollama")
    if path:
        return path

    fallback = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    if fallback.exists():
        return str(fallback)

    raise RuntimeError("Ollama not found.")


def verify(hypothesis: str, evidence: Dict) -> Dict:
    ollama = resolve_ollama_path()

    prompt = SYSTEM_PROMPT + f"""
HYPOTHESIS:
{hypothesis}

EVIDENCE:
{json.dumps(evidence, indent=2)}
"""

    process = subprocess.run(
        [ollama, "run", "llama3"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        return {
            "supported": False,
            "confidence": 0.0,
            "reason": "Unable to verify hypothesis"
        }
