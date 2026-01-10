import typer
from rich.console import Console
from pathlib import Path
from opspilot.agents.planner import plan

from opspilot.state import AgentState
from opspilot.config import load_config
from opspilot.context.project import scan_project_tree
from opspilot.context.logs import read_logs
from opspilot.context.env import read_env
from opspilot.context.docker import read_docker_files
from opspilot.context.deps import read_dependencies
from opspilot.tools.log_tools import analyze_log_errors
from opspilot.tools.env_tools import find_missing_env
from opspilot.tools.dep_tools import has_dependency
from opspilot.agents.verifier import verify
from opspilot.agents.fixer import suggest
from opspilot.diffs.redis import redis_timeout_diff, redis_pooling_diff
from opspilot.memory import save_memory
from opspilot.memory import find_similar_issues

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

    past = find_similar_issues(project_root)
    if past:
        console.print(
            "[magenta]🧠 Similar issues detected from past runs:[/magenta]")
        for p in past[-2:]:
            console.print(
                f"- {p['hypothesis']} (confidence {p['confidence']})")

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

    console.print("[cyan]🧠 Planner Agent reasoning...[/cyan]")
    console.print("[debug] entering planner")

    with console.status("[cyan]Analyzing project context with LLM...[/cyan]", spinner="dots"):
        plan_result = plan(state.context)
    console.print("[debug] planner done")

    state.hypothesis = plan_result.get("hypothesis")
    state.confidence = plan_result.get("confidence")
    state.checks_remaining = plan_result.get("required_checks", [])

    if "error" in plan_result:
        console.print("[bold red]⚠ Planner Error:[/bold red]", plan_result["error"])

    console.print("[bold yellow]Hypothesis:[/bold yellow]", state.hypothesis)
    console.print("[bold yellow]Confidence:[/bold yellow]", state.confidence)

    console.print("[debug] collecting evidence")
    evidence = {}

    # Tool 1: logs
    log_counts = analyze_log_errors(state.context.get("logs"))
    if log_counts:
        evidence["log_errors"] = log_counts

    # Tool 2: env check (example)
    required_envs = ["REDIS_URL"]
    missing = find_missing_env(required_envs, state.context.get("env", {}))
    if missing:
        evidence["missing_env"] = missing

    # Tool 3: deps
    deps = state.context.get("dependencies", [])
    if has_dependency(deps, "redis"):
        evidence["uses_redis"] = True

    console.print("[debug] evidence done")
    console.print("[cyan]🛠 Evidence collected:[/cyan]", evidence)

    if state.hypothesis and evidence:
        console.print("[debug] verifying")
        console.print("[cyan]🔎 Verifying hypothesis...[/cyan]")
        verdict = verify(state.hypothesis, evidence)
        console.print("[debug] verification done")

        console.print("[bold yellow]Supported:[/bold yellow]",
                      verdict["supported"])
        console.print("[bold yellow]Confidence:[/bold yellow]",
                      verdict["confidence"])
        console.print("[bold yellow]Reason:[/bold yellow]", verdict["reason"])
    else:
        console.print(
            "[yellow]Not enough evidence to verify hypothesis[/yellow]")

    CONFIDENCE_THRESHOLD = 0.6

    if verdict.get("confidence", 0) >= CONFIDENCE_THRESHOLD and state.hypothesis:
        console.print("[debug] suggesting fixes")
        console.print(
            "[cyan]🧩 Generating safe fix suggestions (dry-run)...[/cyan]")

        suggestions = []

        if evidence.get("uses_redis") and "Timeout" in evidence.get("log_errors", {}):
            suggestions.append(redis_timeout_diff())
            suggestions.append(redis_pooling_diff())

        if not suggestions:
            llm_suggestions = suggest(
                state.hypothesis, evidence).get("suggestions", [])
            suggestions.extend(llm_suggestions)

        if suggestions:
            for s in suggestions:
                console.print(f"\n[bold]File:[/bold] {s['file']}")
                console.print(f"[dim]{s['rationale']}[/dim]")
                console.print(s["diff"])
        else:
            console.print("[yellow]No safe suggestions generated.[/yellow]")
        console.print("[debug] fixer done")
    else:
        console.print(
            "[yellow]Confidence too low — not generating fixes.[/yellow]")

    save_memory({
        "project": project_root,
        "hypothesis": state.hypothesis,
        "confidence": verdict.get("confidence"),
        "evidence": evidence
    })
    console.print("\n[bold green]🧾 Final Diagnosis Summary[/bold green]")
    console.print(f"• Hypothesis: {state.hypothesis}")
    console.print(f"• Confidence: {verdict.get('confidence')}")
    console.print(f"• Evidence signals: {list(evidence.keys())}")
    console.print("• Suggested fixes: DRY-RUN ONLY")
