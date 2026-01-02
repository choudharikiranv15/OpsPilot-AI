from pathlib import Path
from typing import List


def read_dependencies(project_root: str) -> List[str]:
    root = Path(project_root)

    if (root / "requirements.txt").exists():
        return (root / "requirements.txt").read_text().splitlines()

    if (root / "package.json").exists():
        return ["node_project"]

    return []
