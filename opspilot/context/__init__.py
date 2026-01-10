"""Context gathering modules for OpsPilot."""

from opspilot.context.project import scan_project_tree
from opspilot.context.logs import read_logs
from opspilot.context.env import read_env
from opspilot.context.docker import read_docker_files
from opspilot.context.deps import read_dependencies


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
        "env": read_env(project_root),
        "docker": read_docker_files(project_root),
        "dependencies": read_dependencies(project_root),
    }
