from pathlib import Path
from typing import List, Dict


def scan_project_tree(project_root: str, max_depth: int = 3) -> Dict[str, List[str]]:
    root = Path(project_root)
    structure = {}

    for path in root.rglob("*"):
        try:
            depth = len(path.relative_to(root).parts)
        except ValueError:
            continue

        if depth <= max_depth and path.is_file():
            structure.setdefault(
                str(path.parent.relative_to(root)), []).append(path.name)

    return structure
