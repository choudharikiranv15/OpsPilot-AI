from typing import Dict
import json
from opspilot.utils.llm import call_llama, safe_json_parse

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
    prompt = SYSTEM_PROMPT + f"""
HYPOTHESIS:
{hypothesis}

EVIDENCE:
{json.dumps(evidence, indent=2)}
"""

    try:
        # Use multi-provider LLM system with automatic fallback
        raw_output = call_llama(prompt, timeout=120)

        if not raw_output:
            print(f"[ERROR] Verifier LLM returned empty response")
            return {
                "supported": False,
                "confidence": 0.0,
                "reason": "LLM verification failed"
            }

        # Parse JSON response using safe parser
        result = safe_json_parse(raw_output)

        if result and "supported" in result:
            return result
        else:
            print(f"[ERROR] Invalid verifier response format: {raw_output}")
            return {
                "supported": False,
                "confidence": 0.0,
                "reason": "Unable to verify hypothesis"
            }

    except Exception as e:
        print(f"[ERROR] Verifier failed: {e}")
        return {
            "supported": False,
            "confidence": 0.0,
            "reason": f"Verification error: {str(e)}"
        }
