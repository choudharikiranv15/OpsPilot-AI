import typer
from rich.console import Console
from pathlib import Path
import sys
import os
import json
from datetime import datetime

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    # Enable UTF-8 mode on Windows
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass  # Fallback for older Python or non-standard terminals

from dotenv import load_dotenv
from opspilot.agents.planner import plan
from opspilot.state import AgentState
from opspilot.constants import VERSION, CONFIDENCE_THRESHOLD, BUILD_CMD_TIMEOUT
from opspilot.logger import setup_logging, get_logger
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
from opspilot.utils.llm import check_any_llm_available, get_llm_router
from opspilot.tools.env_tools import find_missing_env
from opspilot.tools.dep_tools import has_dependency
from opspilot.agents.verifier import verify
from opspilot.agents.fixer import suggest
from opspilot.agents.remediation import generate_remediation_plan, format_remediation_output
from opspilot.diffs.redis import redis_timeout_diff, redis_pooling_diff
from opspilot.memory import save_memory
from opspilot.memory import find_similar_issues
# Redis memory backend (with fallback to file-based)
try:
    from opspilot.memory_redis import get_memory_backend
    redis_memory = get_memory_backend(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        fallback_to_file=True
    )
except Exception:
    redis_memory = None  # Will use file-based fallback
from opspilot.graph.engine import run_agent



# Load environment variables from .env file (searches in current directory and parents)
load_dotenv(verbose=False, override=False)  # Don't override existing env vars

app = typer.Typer(help="OpsPilot - Agentic AI CLI for incident analysis")
console = Console()

__version__ = VERSION


def version_callback(value: bool):
    if value:
        console.print(f"OpsPilot version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show OpsPilot version and exit"
    )
):
    """
    OpsPilot CLI entry point.
    """
    pass


def save_report(output_file: str, result: dict, console: Console):
    """
    Save analysis report to file.

    Supports .json, .md, and .txt formats.
    """
    output_path = Path(output_file)
    ext = output_path.suffix.lower()

    try:
        if ext == ".json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            console.print(f"[green]Report saved to {output_file}[/green]")

        elif ext == ".md":
            md_content = generate_markdown_report(result)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            console.print(f"[green]Markdown report saved to {output_file}[/green]")

        elif ext == ".txt":
            txt_content = generate_text_report(result)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(txt_content)
            console.print(f"[green]Text report saved to {output_file}[/green]")

        else:
            # Default to JSON
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            console.print(f"[green]Report saved to {output_file} (JSON format)[/green]")

    except Exception as e:
        console.print(f"[red]Failed to save report: {e}[/red]")


def generate_markdown_report(result: dict) -> str:
    """Generate a markdown-formatted report."""
    lines = [
        "# OpsPilot Analysis Report",
        "",
        f"**Generated:** {result.get('timestamp', 'N/A')}",
        f"**Project:** {result.get('project', 'N/A')}",
        "",
        "## Diagnosis",
        "",
        f"**Hypothesis:** {result.get('hypothesis', 'No hypothesis generated')}",
        "",
        f"**Confidence:** {result.get('confidence', 0.0)}",
        "",
    ]

    # Verdict
    verdict = result.get("verdict")
    if verdict:
        lines.extend([
            "### Verification",
            "",
            f"- **Supported:** {verdict.get('supported', False)}",
            f"- **Confidence:** {verdict.get('confidence', 0.0)}",
            f"- **Reason:** {verdict.get('reason', 'N/A')}",
            "",
        ])

    # Evidence
    evidence = result.get("evidence", {})
    if evidence:
        lines.extend([
            "## Evidence",
            "",
        ])

        if evidence.get("severity"):
            lines.append(f"**Severity:** {evidence['severity']}")

        if evidence.get("build_errors"):
            build = evidence["build_errors"]
            lines.extend([
                "",
                "### Build Errors",
                "",
                f"- **Error Count:** {build.get('error_count', 0)}",
                f"- **Error Types:** {', '.join(build.get('error_types', []))}",
                f"- **Files Affected:** {', '.join(build.get('files_affected', []))}",
            ])

        lines.append("")

    # Suggestions
    suggestions = result.get("suggestions", [])
    if suggestions:
        lines.extend([
            "## Suggested Fixes",
            "",
        ])
        for i, s in enumerate(suggestions, 1):
            lines.extend([
                f"### Fix {i}: {s.get('file', 'unknown')}",
                "",
                f"**Rationale:** {s.get('rationale', '')}",
                "",
                "```diff",
                s.get('diff', ''),
                "```",
                "",
            ])

    lines.extend([
        "---",
        "",
        "*Report generated by OpsPilot*",
    ])

    return "\n".join(lines)


def generate_text_report(result: dict) -> str:
    """Generate a plain text report."""
    lines = [
        "=" * 60,
        "OPSPILOT ANALYSIS REPORT",
        "=" * 60,
        "",
        f"Generated: {result.get('timestamp', 'N/A')}",
        f"Project: {result.get('project', 'N/A')}",
        "",
        "-" * 60,
        "DIAGNOSIS",
        "-" * 60,
        "",
        f"Hypothesis: {result.get('hypothesis', 'No hypothesis generated')}",
        f"Confidence: {result.get('confidence', 0.0)}",
        "",
    ]

    verdict = result.get("verdict")
    if verdict:
        lines.extend([
            "Verification:",
            f"  Supported: {verdict.get('supported', False)}",
            f"  Confidence: {verdict.get('confidence', 0.0)}",
            f"  Reason: {verdict.get('reason', 'N/A')}",
            "",
        ])

    evidence = result.get("evidence", {})
    if evidence:
        lines.extend([
            "-" * 60,
            "EVIDENCE",
            "-" * 60,
            "",
        ])

        if evidence.get("severity"):
            lines.append(f"Severity: {evidence['severity']}")

        if evidence.get("build_errors"):
            build = evidence["build_errors"]
            lines.extend([
                "",
                "Build Errors:",
                f"  Error Count: {build.get('error_count', 0)}",
                f"  Error Types: {', '.join(build.get('error_types', []))}",
                f"  Files: {', '.join(build.get('files_affected', []))}",
            ])

    lines.extend([
        "",
        "=" * 60,
        "END OF REPORT",
        "=" * 60,
    ])

    return "\n".join(lines)


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
    error_input: str = typer.Option(
        None,
        "--error",
        "-e",
        help="Paste build/runtime error text directly"
    ),
    stdin_input: bool = typer.Option(
        False,
        "--stdin",
        help="Read error input from stdin (for piping: cmd 2>&1 | opspilot analyze --stdin)"
    ),
    build_cmd: str = typer.Option(
        None,
        "--build-cmd",
        help="Run build command and capture errors (e.g., 'ng serve', 'npm run build')"
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
    output_file: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Save analysis report to file (supports .json, .md, .txt)"
    ),
    min_confidence: float = typer.Option(
        None,
        "--min-confidence",
        help=f"Override minimum confidence threshold (default: {CONFIDENCE_THRESHOLD})"
    ),
):
    """
    Analyze the current project for runtime issues.

    Examples:
        opspilot analyze                          # Quick analysis
        opspilot analyze --mode deep              # Deep analysis
        opspilot analyze --error "error text"     # Analyze specific error
        opspilot analyze --output report.json     # Save report to file
        ng serve 2>&1 | opspilot analyze --stdin  # Pipe build errors
    """
    if mode not in {"quick", "deep", "explain"}:
        raise typer.BadParameter("Mode must be quick, deep, or explain")

    try:
        # Check LLM availability (any provider)
        if not check_any_llm_available():
            router = get_llm_router()
            console.print(
                "[red]ERROR:[/red] No LLM provider available.\n\n"
                "[bold]Setup at least one FREE/open-source provider:[/bold]\n\n"
                "1. [cyan]Ollama[/cyan] (local, 100% free & private)\n"
                "   curl -fsSL https://ollama.ai/install.sh | sh\n"
                "   ollama pull llama3\n\n"
                "2. [cyan]Google Gemini[/cyan] (cloud, free tier)\n"
                "   Get key: https://aistudio.google.com/\n"
                "   export GOOGLE_API_KEY='your-key'\n\n"
                "3. [cyan]OpenRouter[/cyan] (cloud, free models)\n"
                "   Get key: https://openrouter.ai/\n"
                "   export OPENROUTER_API_KEY='your-key'\n\n"
                "4. [cyan]HuggingFace[/cyan] (cloud, free tier)\n"
                "   Get key: https://huggingface.co/settings/tokens\n"
                "   export HUGGINGFACE_API_KEY='your-key'"
            )
            raise typer.Exit(code=1)

        # Show which provider will be used
        router = get_llm_router()
        available = router.get_available_providers()
        console.print(f"[dim]LLM providers available: {', '.join(available)}[/dim]")

        project_root = str(Path.cwd())

        past = find_similar_issues(project_root)
        if past:
            console.print(
                "[magenta]Similar issues detected from past runs:[/magenta]")
            for p in past[-2:]:
                console.print(
                    f"- {p.get('hypothesis', 'Unknown')} (confidence {p.get('confidence', 0.0)})")

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

        # Capture build/runtime errors from various sources
        build_errors = None
        error_source = None

        if stdin_input:
            import sys
            import select
            # Check if there's data on stdin (non-blocking)
            if sys.platform == "win32":
                # Windows: just try to read if --stdin is specified
                if not sys.stdin.isatty():
                    build_errors = sys.stdin.read()
                    error_source = "stdin"
            else:
                # Unix: use select to check for available input
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    build_errors = sys.stdin.read()
                    error_source = "stdin"

            if build_errors:
                console.print(f"[cyan]Captured {len(build_errors)} bytes from stdin[/cyan]")
            else:
                console.print("[yellow]Warning: --stdin specified but no input received[/yellow]")

        elif error_input:
            build_errors = error_input
            error_source = "cli"
            console.print(f"[cyan]Using error input from --error flag ({len(build_errors)} bytes)[/cyan]")

        elif build_cmd:
            import subprocess
            console.print(f"[cyan]Running build command: {build_cmd}[/cyan]")
            try:
                result = subprocess.run(
                    build_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=BUILD_CMD_TIMEOUT,
                    cwd=project_root
                )
                # Capture both stdout and stderr
                build_errors = result.stdout + result.stderr
                error_source = "build_cmd"
                if result.returncode != 0:
                    console.print(f"[yellow]Build command failed (exit code {result.returncode})[/yellow]")
                else:
                    console.print("[green]Build command completed[/green]")
            except subprocess.TimeoutExpired:
                console.print(f"[red]Build command timed out after {BUILD_CMD_TIMEOUT}s[/red]")
            except Exception as e:
                console.print(f"[red]Failed to run build command: {e}[/red]")

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
            "build_errors": build_errors,
        }
        console.print("[cyan]Context collected:[/cyan]")
        console.print(f"• Build errors: {bool(build_errors)} ({error_source or 'none'})")
        console.print(f"• Logs found: {bool(state.context['logs'])} ({'production' if production_logs else 'local'})")
        console.print(f"• Env vars: {len(state.context['env'])}")
        console.print(f"• Docker config: {bool(state.context['docker'])}")
        console.print(
            f"• Dependencies detected: {len(state.context['dependencies'])}")

        console.print("[cyan]Planner Agent reasoning...[/cyan]")
        if debug:
            console.print("[dim][debug] entering planner[/dim]")

        with console.status("[cyan]Analyzing project context with LLM...[/cyan]", spinner="dots"):
            plan_result = plan(state.context)
        if debug:
            console.print("[dim][debug] planner done[/dim]")

        state.hypothesis = plan_result.get("hypothesis")
        state.confidence = plan_result.get("confidence")
        state.checks_remaining = plan_result.get("required_checks", [])

        if "error" in plan_result:
            console.print("[bold red]⚠ Planner Error:[/bold red]", plan_result["error"])

        console.print("[bold yellow]Hypothesis:[/bold yellow]", state.hypothesis)
        console.print("[bold yellow]Confidence:[/bold yellow]", state.confidence)

        if debug:
            console.print("[dim][debug] collecting evidence[/dim]")

        # Use centralized evidence collection with pattern analysis
        evidence = collect_evidence(state.context)

        if debug:
            console.print("[dim][debug] evidence done[/dim]")

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
                        console.print(f"[yellow]{correlation.get('reason', '')}[/yellow]")
                        console.print("\n[bold yellow]Suspicious Commits:[/bold yellow]")
                        for commit in correlation.get("suspicious_commits", [])[:3]:
                            console.print(f"  [{commit.get('hash', 'unknown')}] {commit.get('message', '')}")
                            console.print(f"    Time diff: {commit.get('time_diff_hours', '?')}h before error")
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
            if debug:
                console.print("[dim][debug] verifying[/dim]")
            console.print("[cyan]Verifying hypothesis...[/cyan]")
            verdict = verify(state.hypothesis, evidence)
            if debug:
                console.print("[dim][debug] verification done[/dim]")

            console.print("[bold yellow]Supported:[/bold yellow]",
                          verdict.get("supported", False))
            console.print("[bold yellow]Confidence:[/bold yellow]",
                          verdict.get("confidence", 0.0))
            console.print("[bold yellow]Reason:[/bold yellow]", verdict.get("reason", "N/A"))
        else:
            console.print(
                "[yellow]Not enough evidence to verify hypothesis[/yellow]")

        # Use overridden confidence or default
        threshold = min_confidence if min_confidence is not None else CONFIDENCE_THRESHOLD

        if verdict and verdict.get("confidence", 0) >= threshold and state.hypothesis:
            if debug:
                console.print("[dim][debug] suggesting fixes[/dim]")
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
                    console.print(f"\n[bold]File:[/bold] {s.get('file', 'unknown')}")
                    console.print(f"[dim]{s.get('rationale', '')}[/dim]")
                    console.print(s.get("diff", ""))

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
            if debug:
                console.print("[dim][debug] fixer done[/dim]")
        else:
            console.print(
                "[yellow]Confidence too low — not generating fixes.[/yellow]")

        save_memory({
            "project": project_root,
            "hypothesis": state.hypothesis,
            "confidence": verdict.get("confidence") if verdict else 0.0,
            "evidence": evidence
        })
        console.print("\n[bold green]Final Diagnosis Summary[/bold green]")
        console.print(f"• Hypothesis: {state.hypothesis}")
        console.print(f"• Confidence: {state.confidence}")
        console.print(f"• Evidence signals: {list(state.evidence.keys())}")
        console.print("• Suggested fixes: DRY-RUN ONLY")

        # Build complete result
        result = {
            "project": project_root,
            "hypothesis": state.hypothesis,
            "confidence": state.confidence,
            "evidence": state.evidence,
            "suggestions": state.suggestions,
            "verdict": {
                "supported": verdict.get("supported") if verdict else False,
                "confidence": verdict.get("confidence") if verdict else 0.0,
                "reason": verdict.get("reason") if verdict else None,
            } if verdict else None,
            "timestamp": datetime.now().isoformat(),
        }

        # Save to output file if specified
        if output_file:
            save_report(output_file, result, console)

        if output_json:
            print(json.dumps(result, indent=2, default=str))
            return

        # Use overridden confidence or default
        threshold = min_confidence if min_confidence is not None else CONFIDENCE_THRESHOLD

        if not state.hypothesis or (state.confidence or 0) < threshold:
            console.print(
                f"[yellow]No confident diagnosis could be made. Evidence insufficient (threshold: {threshold}).[/yellow]"
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
