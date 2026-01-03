from typing import Dict, List


def find_missing_env(required_keys: List[str], env: Dict[str, str]) -> List[str]:
    return [k for k in required_keys if k not in env]
