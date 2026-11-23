def find_missing_env(required_keys: list[str], env: dict[str, str]) -> list[str]:
    return [k for k in required_keys if k not in env]
