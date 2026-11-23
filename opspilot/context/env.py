"""Environment variable file parsing.

Security note: OpsPilot only ever exposes environment variable *names* to the
rest of the pipeline (context, reports, prompts). Values are parsed solely to
determine names and are discarded immediately; see ``read_env_names``.
"""

import os
import re
from pathlib import Path

ENV_FILE_CANDIDATES = (".env", ".env.local", ".env.development", ".env.production")


def read_env_names(project_root: str) -> list[str]:
    """
    Return the sorted, de-duplicated variable names defined in the project's
    .env files (.env, .env.local, .env.development, .env.production).

    Values are never returned, stored, or logged.
    """
    names: set[str] = set()
    for name in ENV_FILE_CANDIDATES:
        path = Path(project_root) / name
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except (PermissionError, OSError):
            continue
        names.update(parse_env_content(content).keys())
    return sorted(names)


def _read_env_values(project_root: str) -> dict[str, str]:
    """
    Internal helper: parse the first .env file found, including values.

    Never pass the result to context, reports, logs, or LLM prompts.
    """
    for name in ENV_FILE_CANDIDATES:
        path = Path(project_root) / name
        if path.is_file():
            try:
                return parse_env_content(
                    path.read_text(encoding="utf-8", errors="ignore")
                )
            except (PermissionError, OSError):
                return {}
    return {}


def parse_env_content(content: str) -> dict[str, str]:
    """
    Parse .env file content into a dictionary.

    Args:
        content: Raw content of .env file

    Returns:
        Dictionary of environment variables
    """
    env_vars = {}
    lines = content.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        i += 1

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Handle export prefix
        if line.startswith("export "):
            line = line[7:].strip()

        # Skip if no equals sign
        if "=" not in line:
            continue

        # Split on first equals
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Skip invalid keys
        if not key or not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
            continue

        # Handle quoted values
        if (
            value.startswith('"')
            and value.endswith('"')
            or value.startswith("'")
            and value.endswith("'")
        ):
            value = value[1:-1]
        elif value.startswith('"') and not value.endswith('"'):
            # Multi-line quoted value
            multi_value = [value[1:]]
            while i < len(lines) and not lines[i].rstrip().endswith('"'):
                multi_value.append(lines[i])
                i += 1
            if i < len(lines):
                multi_value.append(lines[i].rstrip()[:-1])
                i += 1
            value = "\n".join(multi_value)

        # Remove inline comments (not in quoted values)
        if "#" in value and not (value.startswith('"') or value.startswith("'")):
            value = value.split("#")[0].strip()

        # Unescape common escape sequences
        value = value.replace("\\n", "\n")
        value = value.replace("\\t", "\t")
        value = value.replace('\\"', '"')
        value = value.replace("\\'", "'")

        env_vars[key] = value

    return env_vars


_ENV_REFERENCE_PATTERNS = [
    re.compile(r"process\.env\.([A-Z_][A-Z0-9_]*)"),  # Node.js
    re.compile(r"process\.env\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]"),  # Node.js
    re.compile(r"os\.environ\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]"),  # Python
    re.compile(r"os\.environ\.get\(['\"]([A-Z_][A-Z0-9_]*)['\"]"),  # Python
    re.compile(r"os\.getenv\(['\"]([A-Z_][A-Z0-9_]*)['\"]"),  # Python
    re.compile(r"ENV\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]"),  # Ruby
    re.compile(r"os\.Getenv\(['\"]([A-Z_][A-Z0-9_]*)['\"]\)"),  # Go
    re.compile(r"getenv\(['\"]([A-Z_][A-Z0-9_]*)['\"]\)"),  # PHP / C
]
_SOURCE_EXTENSIONS = {
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".jsx",
    ".tsx",
    ".py",
    ".rb",
    ".go",
    ".php",
}
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "vendor",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
    "coverage",
    "bower_components",
}
MAX_SCAN_DEPTH = 4
MAX_SCAN_FILES = 2000
MAX_SCAN_FILE_BYTES = 512 * 1024


def find_env_references(project_root: str) -> dict[str, str]:
    """
    Map environment variable names referenced in source code to the first
    file (relative path) that references them.

    The walk prunes dependency/build directories and is bounded by depth,
    file count and file size, so it stays fast on large repositories.
    """
    root = Path(project_root).resolve()
    found: dict[str, str] = {}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        if depth >= MAX_SCAN_DEPTH:
            dirnames[:] = []
        for name in sorted(filenames):
            if Path(name).suffix not in _SOURCE_EXTENSIONS:
                continue
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > MAX_SCAN_FILE_BYTES:
                    continue
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            scanned += 1
            rel = path.relative_to(root).as_posix()
            for pattern in _ENV_REFERENCE_PATTERNS:
                for var in pattern.findall(content):
                    found.setdefault(var, rel)
            if scanned >= MAX_SCAN_FILES:
                return found
    return found


def get_required_env_vars(project_root: str) -> list[str]:
    """Names of environment variables referenced in source code."""
    return sorted(find_env_references(project_root))


def find_undefined_env_vars(project_root: str) -> dict[str, str]:
    """
    Variables referenced in code but not defined in any project .env file,
    mapped to the file that references them. Names only, never values.
    """
    defined = set(read_env_names(project_root))
    return {
        name: where
        for name, where in sorted(find_env_references(project_root).items())
        if name not in defined
    }
