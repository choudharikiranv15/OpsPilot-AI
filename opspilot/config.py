import json
from pathlib import Path
from typing import Any


def load_config(project_root: str) -> dict[str, Any] | None:
    """
    Load configuration from the project root directory.

    Args:
        project_root: The root directory of the project

    Returns:
        Configuration dictionary if found, None otherwise
    """
    config_path = Path(project_root) / ".opspilot.json"

    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)

    return None
