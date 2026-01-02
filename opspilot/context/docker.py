from pathlib import Path
from typing import Dict


def read_docker_files(project_root: str) -> Dict[str, str]:
    root = Path(project_root)
    docker_data = {}

    dockerfile = root / "Dockerfile"
    if dockerfile.exists():
        docker_data["Dockerfile"] = dockerfile.read_text()

    compose = root / "docker-compose.yml"
    if compose.exists():
        docker_data["docker-compose.yml"] = compose.read_text()

    return docker_data
