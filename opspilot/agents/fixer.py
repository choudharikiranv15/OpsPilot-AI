import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List

SYSTEM_PROMPT = """
You are a senior engineer generating SAFE, DRY-RUN fix suggestions.

Rules:
- Do NOT apply changes
- Do NOT run commands
- Output ONLY suggestions as diffs
- Be minimal and reversible
- If uncertain, say so

Output STRICT JSON:
{
  "suggestions": [
    {
      "file": "path",
      "diff": "unified diff",
      "rationale": "why this helps"
    }
  ]
}
"""

def resolve_ollama_path() -> str:
    p = shutil.which("ollama")
    if p:
        return p
    fb = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    if fb.exists():
        return str(fb)
    raise RuntimeError("Ollama not found.")

def suggest(hypothesis: str, evidence: Dict) -> Dict:
    ollama = resolve_ollama_path()
    prompt = SYSTEM_PROMPT + f"""
HYPOTHESIS:
{hypothesis}

EVIDENCE:
{json.dumps(evidence, indent=2)}
"""
    proc = subprocess.run(
        [ollama, "run", "llama3"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"suggestions": []}
