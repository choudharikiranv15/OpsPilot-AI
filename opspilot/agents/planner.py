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
- PRIORITIZE build_errors if present - these are the actual errors the user is facing
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

    # Prioritize build errors if present
    build_errors = context.get("build_errors")
    if build_errors:
        # Truncate but keep enough to see the error details
        build_errors = build_errors[-4000:]

    summarized_context = {
        "build_errors": build_errors,  # Prioritize build errors
        "logs": context.get("logs", "")[:2000] if context.get("logs") else None,
        "env_vars": list(context.get("env", {}).keys()),
        "docker_present": bool(context.get("docker")),
        "dependencies": context.get("dependencies", [])[:20],
        "structure": str(context.get("structure", ""))[:1000],
    }

    # Customize prompt based on available context
    if build_errors:
        analysis_instruction = "Analyze the BUILD ERRORS first - these are the actual errors the user is experiencing. Focus on the error messages and their causes."
    else:
        analysis_instruction = "Analyze the context and produce a hypothesis."

    user_prompt = f"""
PROJECT CONTEXT:
{json.dumps(summarized_context, indent=2)}

{analysis_instruction}
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
