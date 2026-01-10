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
    try:
        proc = subprocess.run(
            [ollama, "run", "llama3"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120
        )

        if proc.returncode != 0:
            print(f"[ERROR] Fixer LLM failed: {proc.stderr}")
            return {"suggestions": []}

        raw_output = proc.stdout.strip()

        # Try to extract JSON from the output
        start_idx = raw_output.find('{')
        end_idx = raw_output.rfind('}')

        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            json_str = raw_output[start_idx:end_idx + 1]
            return json.loads(json_str)
        else:
            return json.loads(raw_output)

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Fixer LLM timed out after 120s")
        return {"suggestions": []}
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse fixer JSON: {e}")
        print(f"[ERROR] Raw output was: {raw_output}")
        return {"suggestions": []}
