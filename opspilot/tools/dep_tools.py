def has_dependency(deps: list[str], keyword: str) -> bool:
    return any(keyword.lower() in d.lower() for d in deps)
