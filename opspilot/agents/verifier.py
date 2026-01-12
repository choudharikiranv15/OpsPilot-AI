from typing import Dict
import json
import subprocess
from opspilot.utils.llm import resolve_ollama_path

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


def verify(hypothesis: str, evidence: Dict) -> Dict:
    ollama = resolve_ollama_path()

    prompt = SYSTEM_PROMPT + f"""
HYPOTHESIS:
{hypothesis}

EVIDENCE:
{json.dumps(evidence, indent=2)}
"""

    try:
        process = subprocess.run(
            [ollama, "run", "llama3"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120
        )

        if process.returncode != 0:
            print(f"[ERROR] Verifier LLM failed: {process.stderr}")
            return {
                "supported": False,
                "confidence": 0.0,
                "reason": "LLM verification failed"
            }

        raw_output = process.stdout.strip()

        # Try to extract JSON from the output
        start_idx = raw_output.find('{')
        end_idx = raw_output.rfind('}')

        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            json_str = raw_output[start_idx:end_idx + 1]
            return json.loads(json_str)
        else:
            return json.loads(raw_output)

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Verifier LLM timed out after 120s")
        return {
            "supported": False,
            "confidence": 0.0,
            "reason": "Verification timed out"
        }
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse verifier JSON: {e}")
        print(f"[ERROR] Raw output was: {raw_output}")
        return {
            "supported": False,
            "confidence": 0.0,
            "reason": "Unable to verify hypothesis"
        }
