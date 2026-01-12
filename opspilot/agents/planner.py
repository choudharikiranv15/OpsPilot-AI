from typing import Dict
import json
from opspilot.utils.llm import call_llama, safe_json_parse


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
