import typer
from rich.console import Console
from pathlib import Path

from opspilot.state import AgentState
from opspilot.config import load_config
from opspilot.context.project import scan_project_tree
from opspilot.context.logs import read_logs
from opspilot.context.env import read_env
from opspilot.context.docker import read_docker_files
from opspilot.context.deps import read_dependencies

app = typer.Typer(help="OpsPilot - Agentic AI CLI for incident analysis")
console = Console()


@app.callback()
def main():
    """
    OpsPilot CLI entry point.
    """
    pass


@app.command()
def analyze():
    """
    Analyze the current project for runtime issues.
    """
    project_root = str(Path.cwd())

    state = AgentState(project_root=project_root)
    config = load_config(project_root)

    console.print("[bold green]✔ OpsPilot initialized[/bold green]")
    console.print(
        f"[bold green]✔ Project detected[/bold green]: {project_root}")
    console.print(f"Config loaded: {bool(config)}")

    state.context = {
        "structure": scan_project_tree(project_root),
        "logs": read_logs(project_root),
        "env": read_env(project_root),
        "docker": read_docker_files(project_root),
        "dependencies": read_dependencies(project_root),
    }
    console.print("[cyan]Context collected:[/cyan]")
    console.print(f"• Logs found: {bool(state.context['logs'])}")
    console.print(f"• Env vars: {len(state.context['env'])}")
    console.print(f"• Docker config: {bool(state.context['docker'])}")
    console.print(
        f"• Dependencies detected: {len(state.context['dependencies'])}")
