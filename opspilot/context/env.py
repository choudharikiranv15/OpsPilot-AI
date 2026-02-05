"""Environment variable file parsing."""

import re
from pathlib import Path
from typing import Dict, List, Optional


def read_env(project_root: str) -> Dict[str, str]:
    """
    Read environment variables from .env file.

    Handles:
    - Standard KEY=value format
    - Quoted values: KEY="value with spaces"
    - Values with equals signs: KEY=value=with=equals
    - Comments (# and inline comments)
    - export KEY=value format
    - Multi-line values (quoted)

    Args:
        project_root: Root directory of the project

    Returns:
        Dictionary of environment variable names to values
    """
    env_path = Path(project_root) / ".env"
    env_vars = {}

    if not env_path.exists():
        # Also check for .env.local, .env.development, etc.
        for alt_name in [".env.local", ".env.development", ".env.production"]:
            alt_path = Path(project_root) / alt_name
            if alt_path.exists():
                env_path = alt_path
                break
        else:
            return env_vars

    try:
        content = env_path.read_text(errors='ignore')
        env_vars = parse_env_content(content)
    except (PermissionError, OSError):
        pass

    return env_vars


def parse_env_content(content: str) -> Dict[str, str]:
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
        if not line or line.startswith('#'):
            continue

        # Handle export prefix
        if line.startswith('export '):
            line = line[7:].strip()

        # Skip if no equals sign
        if '=' not in line:
            continue

        # Split on first equals
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()

        # Skip invalid keys
        if not key or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
            continue

        # Handle quoted values
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
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
            value = '\n'.join(multi_value)

        # Remove inline comments (not in quoted values)
        if '#' in value and not (value.startswith('"') or value.startswith("'")):
            value = value.split('#')[0].strip()

        # Unescape common escape sequences
        value = value.replace('\\n', '\n')
        value = value.replace('\\t', '\t')
        value = value.replace('\\"', '"')
        value = value.replace("\\'", "'")

        env_vars[key] = value

    return env_vars


def get_required_env_vars(project_root: str) -> List[str]:
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
        r'process\.env\.([A-Z_][A-Z0-9_]*)',  # Node.js
        r'os\.environ\[[\'"](.*?)[\'"]\]',    # Python
        r'os\.getenv\([\'"](.*?)[\'"]\)',     # Python
        r'ENV\[[\'"](.*?)[\'"]\]',            # Ruby
        r'os\.Getenv\([\'"](.*?)[\'"]\)',     # Go
        r'\$\{([A-Z_][A-Z0-9_]*)\}',          # Shell-style ${VAR}
        r'getenv\([\'"](.*?)[\'"]\)',         # PHP
    ]

    # File extensions to scan
    extensions = ['.js', '.ts', '.jsx', '.tsx', '.py', '.rb', '.go', '.php']

    # Scan source files (limit depth)
    for ext in extensions:
        for f in root.rglob(f'*{ext}'):
            # Skip node_modules, venv, etc.
            if any(skip in str(f) for skip in ['node_modules', 'venv', '.venv', 'vendor', '__pycache__']):
                continue

            # Limit to top 3 levels
            if len(f.relative_to(root).parts) > 4:
                continue

            try:
                content = f.read_text(errors='ignore')
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    required_vars.update(matches)
            except (PermissionError, OSError):
                continue

    return sorted(list(required_vars))


def validate_env(project_root: str) -> Dict[str, Optional[str]]:
    """
    Validate environment variables against what appears to be required.

    Returns:
        Dictionary mapping variable names to their values (None if missing)
    """
    env_vars = read_env(project_root)
    required = get_required_env_vars(project_root)

    result = {}
    for var in required:
        result[var] = env_vars.get(var)

    return result
