from collections.abc import Collection


def find_missing_env(required_keys: list[str], env: Collection[str]) -> list[str]:
    """Return the required variable names that are not defined (names only)."""
    return [k for k in required_keys if k not in env]
