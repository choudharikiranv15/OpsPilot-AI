from typing import Dict
import json
from opspilot.utils.llm import call_llama, safe_json_parse


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
