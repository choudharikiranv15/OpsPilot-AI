from typing import List


def has_dependency(deps: List[str], keyword: str) -> bool:
    return any(keyword.lower() in d.lower() for d in deps)
