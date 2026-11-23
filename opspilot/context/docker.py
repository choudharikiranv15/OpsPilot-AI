"""Docker configuration detection.

Only file *names* are reported. File contents can embed credentials
(build args, environment blocks), so they are never read into context.
"""

from pathlib import Path

DOCKER_FILE_CANDIDATES = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


def find_docker_files(project_root: str) -> list[str]:
    """Return the Docker-related files present in the project root."""
    root = Path(project_root)
    return [name for name in DOCKER_FILE_CANDIDATES if (root / name).is_file()]
