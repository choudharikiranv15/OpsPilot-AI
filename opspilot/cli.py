import typer
from rich.console import Console
from pathlib import Path
from opspilot.agents.planner import plan
import json
from opspilot.state import AgentState
from opspilot.config import load_config
from opspilot.context import collect_context
from opspilot.context.project import scan_project_tree
from opspilot.context.logs import read_logs
from opspilot.context.env import read_env
from opspilot.context.docker import read_docker_files
from opspilot.context.deps import read_dependencies
from opspilot.context.production_logs import auto_detect_and_fetch
from opspilot.context.deployment_history import analyze_deployment_impact, format_deployment_analysis, correlate_with_error_timeline
from opspilot.tools import collect_evidence
from opspilot.tools.log_tools import analyze_log_errors
from opspilot.utils.llm import check_ollama_available
from opspilot.tools.env_tools import find_missing_env
from opspilot.tools.dep_tools import has_dependency
from opspilot.agents.verifier import verify
from opspilot.agents.fixer import suggest
from opspilot.agents.remediation import generate_remediation_plan, format_remediation_output
from opspilot.diffs.redis import redis_timeout_diff, redis_pooling_diff
from opspilot.memory import save_memory
from opspilot.memory import find_similar_issues
from opspilot.graph.engine import run_agent
from opspilot.state import AgentState



app = typer.Typer(help="OpsPilot - Agentic AI CLI for incident analysis")
console = Console()


@app.callback()
def main():
    """
    OpsPilot CLI entry point.
    """
    pass


@app.command()
def analyze(
     mode: str = typer.Option(
        "quick",
        help="Execution mode: quick | deep | explain"
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show additional details"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show debug logs"
    ),
    log_source: str = typer.Option(
        None,
        "--log-source",
        help="Production log source: URL, s3://bucket/key, k8s://namespace/pod, cw://log-group/stream, or file path"
    ),
    deployment_analysis: bool = typer.Option(
        False,
        "--deployment-analysis",
        help="Analyze recent Git deployments for correlation"
    ),
    since_hours: int = typer.Option(
        24,
        "--since-hours",
        help="Hours to look back for deployment analysis (default: 24)"
    ),
):
    """
    Analyze the current project for runtime issues.
    """
    if mode not in {"quick", "deep", "explain"}:
        raise typer.BadParameter("Mode must be quick, deep, or explain")

    try:
        # Check Ollama availability
        if not check_ollama_available():
            console.print(
                "[red]ERROR:[/red] Ollama not found or not running.\n"
                "Install from: https://ollama.ai/ and run: ollama pull llama3"
            )
            raise typer.Exit(code=1)

        project_root = str(Path.cwd())

        past = find_similar_issues(project_root)
        if past:
            console.print(
                "[magenta]Similar issues detected from past runs:[/magenta]")
            for p in past[-2:]:
                console.print(
                    f"- {p['hypothesis']} (confidence {p['confidence']})")

        state = AgentState(project_root=project_root)

        if mode == "explain":
            # No LLM at all
            state.context = collect_context(project_root)
            state.evidence = collect_evidence(state.context)

        elif mode == "quick":
            # One planner pass only
            state.max_iterations = 1
            state = run_agent(state)

        elif mode == "deep":
            # Full agent loop (default)
            state = run_agent(state)

        config = load_config(project_root)

        console.print("[bold green]OpsPilot initialized[/bold green]")
        console.print(
            f"[bold green]Project detected[/bold green]: {project_root}")
        console.print(f"Config loaded: {bool(config)}")

        # Fetch production logs if specified
        production_logs = None
        if log_source:
            console.print(f"[cyan]Fetching production logs from: {log_source}[/cyan]")
            production_logs = auto_detect_and_fetch(log_source)
            if production_logs:
                console.print(f"[green]Successfully fetched {len(production_logs)} bytes of logs[/green]")
            else:
                console.print("[yellow]Warning: Could not fetch production logs[/yellow]")

        state.context = {
            "structure": scan_project_tree(project_root),
            "logs": production_logs if production_logs else read_logs(project_root),
            "env": read_env(project_root),
            "docker": read_docker_files(project_root),
            "dependencies": read_dependencies(project_root),
        }
        console.print("[cyan]Context collected:[/cyan]")
        console.print(f"• Logs found: {bool(state.context['logs'])} ({'production' if production_logs else 'local'})")
        console.print(f"• Env vars: {len(state.context['env'])}")
        console.print(f"• Docker config: {bool(state.context['docker'])}")
        console.print(
            f"• Dependencies detected: {len(state.context['dependencies'])}")

        console.print("[cyan]Planner Agent reasoning...[/cyan]")
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

        # Deployment correlation analysis
        deployment_info = None
        if deployment_analysis:
            console.print("\n[cyan]Analyzing recent deployments...[/cyan]")
            deployment_info = analyze_deployment_impact(project_root, since_hours)

            if deployment_info and deployment_info.get("has_recent_changes"):
                formatted_deployment = format_deployment_analysis(deployment_info)
                console.print(formatted_deployment)

                # Correlate with error timeline if available
                if evidence.get("timeline") and evidence["timeline"].get("first_seen"):
                    correlation = correlate_with_error_timeline(
                        deployment_info.get("commits", []),
                        evidence["timeline"]["first_seen"]
                    )

                    if correlation.get("correlation") == "strong":
                        console.print("\n[bold red]DEPLOYMENT CORRELATION DETECTED![/bold red]")
                        console.print(f"[yellow]{correlation.get('reason')}[/yellow]")
                        console.print("\n[bold yellow]Suspicious Commits:[/bold yellow]")
                        for commit in correlation.get("suspicious_commits", [])[:3]:
                            console.print(f"  [{commit['hash']}] {commit['message']}")
                            console.print(f"    Time diff: {commit['time_diff_hours']}h before error")
            else:
                console.print("[green]No recent deployments detected[/green]")

        # Display severity and error summary
        if evidence.get("severity"):
            severity = evidence["severity"]
            severity_color = {
                "P0": "bold red",
                "P1": "bold orange1",
                "P2": "bold yellow",
                "P3": "bold blue"
            }.get(severity, "white")

            console.print(f"\n[{severity_color}]SEVERITY: {severity}[/{severity_color}]")

            if evidence.get("error_count"):
                console.print(f"[white]Total Errors: {evidence['error_count']}[/white]")

            # Show timeline if available
            if evidence.get("timeline"):
                timeline = evidence["timeline"]
                console.print(f"[white]First Seen: {timeline.get('first_seen', 'unknown')}[/white]")
                console.print(f"[white]Occurrences: {timeline.get('total_occurrences', 0)}[/white]")

        console.print("\n[cyan]Evidence collected:[/cyan]", evidence)

        verdict = None
        if state.hypothesis and evidence:
            console.print("[debug] verifying")
            console.print("[cyan]Verifying hypothesis...[/cyan]")
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

        if verdict and verdict.get("confidence", 0) >= CONFIDENCE_THRESHOLD and state.hypothesis:
            console.print("[debug] suggesting fixes")
            console.print(
                "[cyan]Generating safe fix suggestions (dry-run)...[/cyan]")

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

                # Generate and display remediation plan
                console.print("\n[bold cyan]Generating Remediation Plan...[/bold cyan]")
                remediation_plan = generate_remediation_plan(
                    state.hypothesis,
                    evidence,
                    suggestions
                )
                formatted_plan = format_remediation_output(remediation_plan)
                console.print(formatted_plan)
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
        console.print("\n[bold green]Final Diagnosis Summary[/bold green]")
        console.print(f"• Hypothesis: {state.hypothesis}")
        console.print(f"• Confidence: {state.confidence}")
        console.print(f"• Evidence signals: {list(state.evidence.keys())}")
        console.print("• Suggested fixes: DRY-RUN ONLY")

        result = {
            "project": project_root,
            "hypothesis": state.hypothesis,
            "confidence": state.confidence,
            "evidence": state.evidence,
            "suggestions": state.suggestions,
        }

        if output_json:
            print(json.dumps(result, indent=2))
            return

        if not state.hypothesis or state.confidence < 0.6:
            console.print(
                "[yellow]No confident diagnosis could be made. Evidence insufficient.[/yellow]"
            )
            return

    except KeyboardInterrupt:
        console.print("\n[yellow]Analysis interrupted by user[/yellow]")
        raise typer.Exit(code=130)
    except FileNotFoundError as e:
        console.print(f"[red]ERROR:[/red] File not found: {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]FATAL ERROR:[/red] Analysis failed: {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(code=1)
