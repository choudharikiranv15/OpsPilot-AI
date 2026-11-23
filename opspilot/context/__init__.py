"""Context gathering modules for OpsPilot."""

from opspilot.context.deps import read_dependencies
from opspilot.context.docker import find_docker_files
from opspilot.context.env import read_env_names
from opspilot.context.logs import read_logs
from opspilot.context.project import scan_project_tree


def collect_context(project_root: str) -> dict:
    """
    Collect all project context from various sources.

    Args:
        project_root: Root directory of the project

    Returns:
        Dictionary containing all context information
    """
    return {
        "structure": scan_project_tree(project_root),
        "logs": read_logs(project_root),
        "env": read_env_names(project_root),
        "docker": find_docker_files(project_root),
        "dependencies": read_dependencies(project_root),
    }
