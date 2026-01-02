from pathlib import Path
from typing import Dict


def read_env(project_root: str) -> Dict[str, str]:
    env_path = Path(project_root) / ".env"
    env_vars = {}

    if not env_path.exists():
        return env_vars

    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    return env_vars
