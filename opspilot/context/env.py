"""Environment variable file parsing.

Security note: OpsPilot only ever exposes environment variable *names* to the
rest of the pipeline (context, reports, prompts). Values are parsed solely to
determine names and are discarded immediately; see ``read_env_names``.
"""

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


def get_required_env_vars(project_root: str) -> list[str]:
    """
    Detect required environment variables from project files.

    Scans common patterns:
    - process.env.VAR_NAME (Node.js)
    - os.environ['VAR_NAME'] (Python)
    - ENV['VAR_NAME'] (Ruby)
    - os.Getenv("VAR_NAME") (Go)

    Args:
        project_root: Root directory of the project

    Returns:
        List of environment variable names that appear to be required
    """
    root = Path(project_root)
    required_vars = set()

    # Patterns to search for
    patterns = [
        r"process\.env\.([A-Z_][A-Z0-9_]*)",  # Node.js
        r'os\.environ\[[\'"](.*?)[\'"]\]',  # Python
        r'os\.getenv\([\'"](.*?)[\'"]\)',  # Python
        r'ENV\[[\'"](.*?)[\'"]\]',  # Ruby
        r'os\.Getenv\([\'"](.*?)[\'"]\)',  # Go
        r"\$\{([A-Z_][A-Z0-9_]*)\}",  # Shell-style ${VAR}
        r'getenv\([\'"](.*?)[\'"]\)',  # PHP
    ]

    # File extensions to scan
    extensions = [".js", ".ts", ".jsx", ".tsx", ".py", ".rb", ".go", ".php"]

    # Scan source files (limit depth)
    for ext in extensions:
        for f in root.rglob(f"*{ext}"):
            # Skip node_modules, venv, etc.
            if any(
                skip in str(f)
                for skip in ["node_modules", "venv", ".venv", "vendor", "__pycache__"]
            ):
                continue

            # Limit to top 3 levels
            if len(f.relative_to(root).parts) > 4:
                continue

            try:
                content = f.read_text(errors="ignore")
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    required_vars.update(matches)
            except (PermissionError, OSError):
                continue

    return sorted(required_vars)


def find_undefined_env_vars(project_root: str) -> list[str]:
    """
    Return names referenced in source code but not defined in any .env file.

    Only names are returned; values are never read into the result.
    """
    defined = set(read_env_names(project_root))
    return [v for v in get_required_env_vars(project_root) if v not in defined]
