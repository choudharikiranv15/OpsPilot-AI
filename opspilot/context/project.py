from pathlib import Path

# Ignore common large directories that don't need analysis
IGNORE_PATTERNS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    "target",
    ".pytest_cache",
    "coverage",
    ".mypy_cache",
    ".tox",
    "htmlcov",
    "eggs",
    ".eggs",
    "lib",
    "lib64",
    "parts",
    "sdist",
    "wheels",
    "*.egg-info",
    ".DS_Store",
    "vendor",
    "bower_components",
}


def should_ignore(path: Path) -> bool:
    """Check if path should be ignored for performance."""
    parts = path.parts
    return any(pattern in parts for pattern in IGNORE_PATTERNS)


def scan_project_tree(
    project_root: str, max_depth: int = 3, max_files: int = 1000
) -> dict[str, list[str]]:
    """
    Scan project structure with performance optimizations for large codebases.

    Args:
        project_root: Root directory to scan
        max_depth: Maximum depth to traverse (default: 3)
        max_files: Maximum files to include (default: 1000)

    Returns:
        Dictionary mapping directories to file lists
    """
    root = Path(project_root)
    structure = {}
    file_count = 0

    try:
        for path in root.rglob("*"):
            # Early exit if we've scanned enough
            if file_count >= max_files:
                break

            # Skip ignored directories for performance
            if should_ignore(path):
                continue

            try:
                depth = len(path.relative_to(root).parts)
            except ValueError:
                continue

            if depth <= max_depth and path.is_file():
                rel_parent = str(path.parent.relative_to(root))
                structure.setdefault(rel_parent, []).append(path.name)
                file_count += 1

    except Exception:
        # Graceful degradation if scanning fails
        pass

    return structure
