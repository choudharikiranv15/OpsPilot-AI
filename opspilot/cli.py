import json
import os
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    # Enable UTF-8 mode on Windows
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass  # Fallback for older Python or non-standard terminals

from opspilot.agents.fixer import suggest
from opspilot.agents.planner import plan
from opspilot.agents.remediation import (
    format_remediation_output,
    generate_remediation_plan,
)
from opspilot.agents.verifier import verify
from opspilot.config import load_config
from opspilot.constants import BUILD_CMD_TIMEOUT, CONFIDENCE_THRESHOLD, VERSION
from opspilot.context.deployment_history import (
    analyze_deployment_impact,
    correlate_with_error_timeline,
    format_deployment_analysis,
)
from opspilot.context.deps import read_dependencies
from opspilot.context.docker import find_docker_files
from opspilot.context.env import read_env_names
from opspilot.context.logs import read_logs
from opspilot.context.production_logs import LogSourceError, auto_detect_and_fetch
from opspilot.context.project import scan_project_tree
from opspilot.diffs.redis import redis_pooling_diff, redis_timeout_diff
from opspilot.exceptions import LLMError
from opspilot.llm import LLMRouter, ProviderStatus
from opspilot.memory import find_similar_issues, save_memory
from opspilot.settings import get_settings, user_config_file
from opspilot.state import AgentState
from opspilot.tools import collect_evidence

app = typer.Typer(help="OpsPilot - Agentic AI CLI for incident analysis")
console = Console()

__version__ = VERSION


@app.command()
def troubleshoot(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed phase-by-phase analysis"
    ),
    output_json: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON"
    ),
):
    """
    Structured troubleshooting following real SRE debugging patterns.

    Workflow phases:
      1. Logs → What broke (symptoms)
      2. Recent Changes → When did it break (timeline)
      3. Similar Incidents → Has this happened before (history)
      4. Stack Trace → Where did it break (location)
      5. Environment → Configuration issues
      6. Dependencies → Version conflicts
      7. Resources → System limits
      8. External Services → Third-party failures
      9. Root Cause → Hypothesis
      10. Remediation → Action plan

    Examples:
      opspilot troubleshoot              # Quick summary
      opspilot troubleshoot --verbose    # Detailed analysis
      opspilot troubleshoot --json       # JSON output
    """
    from opspilot.commands.troubleshoot import troubleshoot_command

    try:
        troubleshoot_command(
            project_root=str(Path.cwd()), verbose=verbose, output_json=output_json
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Troubleshooting interrupted by user[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as e:
        console.print(f"[red]ERROR:[/red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(code=1) from e


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
        help="Show OpsPilot version and exit",
    ),
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
        lines.extend(
            [
                "### Verification",
                "",
                f"- **Supported:** {verdict.get('supported', False)}",
                f"- **Confidence:** {verdict.get('confidence', 0.0)}",
                f"- **Reason:** {verdict.get('reason', 'N/A')}",
                "",
            ]
        )

    # Evidence
    evidence = result.get("evidence", {})
    if evidence:
        lines.extend(
            [
                "## Evidence",
                "",
            ]
        )

        if evidence.get("severity"):
            lines.append(f"**Severity:** {evidence['severity']}")

        if evidence.get("build_errors"):
            build = evidence["build_errors"]
            lines.extend(
                [
                    "",
                    "### Build Errors",
                    "",
                    f"- **Error Count:** {build.get('error_count', 0)}",
                    f"- **Error Types:** {', '.join(build.get('error_types', []))}",
                    f"- **Files Affected:** {', '.join(build.get('files_affected', []))}",
                ]
            )

        lines.append("")

    # Suggestions
    suggestions = result.get("suggestions", [])
    if suggestions:
        lines.extend(
            [
                "## Suggested Fixes",
                "",
            ]
        )
        for i, s in enumerate(suggestions, 1):
            lines.extend(
                [
                    f"### Fix {i}: {s.get('file', 'unknown')}",
                    "",
                    f"**Rationale:** {s.get('rationale', '')}",
                    "",
                    "```diff",
                    s.get("diff", ""),
                    "```",
                    "",
                ]
            )

    lines.extend(
        [
            "---",
            "",
            "*Report generated by OpsPilot*",
        ]
    )

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
        lines.extend(
            [
                "Verification:",
                f"  Supported: {verdict.get('supported', False)}",
                f"  Confidence: {verdict.get('confidence', 0.0)}",
                f"  Reason: {verdict.get('reason', 'N/A')}",
                "",
            ]
        )

    evidence = result.get("evidence", {})
    if evidence:
        lines.extend(
            [
                "-" * 60,
                "EVIDENCE",
                "-" * 60,
                "",
            ]
        )

        if evidence.get("severity"):
            lines.append(f"Severity: {evidence['severity']}")

        if evidence.get("build_errors"):
            build = evidence["build_errors"]
            lines.extend(
                [
                    "",
                    "Build Errors:",
                    f"  Error Count: {build.get('error_count', 0)}",
                    f"  Error Types: {', '.join(build.get('error_types', []))}",
                    f"  Files: {', '.join(build.get('files_affected', []))}",
                ]
            )

    lines.extend(
        [
            "",
            "=" * 60,
            "END OF REPORT",
            "=" * 60,
        ]
    )

    return "\n".join(lines)


@app.command()
def analyze(
    mode: str = typer.Option("quick", help="Execution mode: quick | deep | explain"),
    output_json: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show additional details"),
    debug: bool = typer.Option(False, "--debug", help="Show debug logs"),
    log_source: str = typer.Option(
        None,
        "--log-source",
        help="Production log source: URL, s3://bucket/key, k8s://namespace/pod, cw://log-group/stream, or file path",
    ),
    error_input: str = typer.Option(
        None, "--error", "-e", help="Paste build/runtime error text directly"
    ),
    stdin_input: bool = typer.Option(
        False,
        "--stdin",
        help="Read error input from stdin (for piping: cmd 2>&1 | opspilot analyze --stdin)",
    ),
    build_cmd: str = typer.Option(
        None,
        "--build-cmd",
        help="Run build command and capture errors (e.g., 'ng serve', 'npm run build')",
    ),
    deployment_analysis: bool = typer.Option(
        False,
        "--deployment-analysis",
        help="Analyze recent Git deployments for correlation",
    ),
    since_hours: int = typer.Option(
        24,
        "--since-hours",
        help="Hours to look back for deployment analysis (default: 24)",
    ),
    output_file: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Save analysis report to file (supports .json, .md, .txt)",
    ),
    min_confidence: float = typer.Option(
        None,
        "--min-confidence",
        help=f"Override minimum confidence threshold (default: {CONFIDENCE_THRESHOLD})",
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        help="LLM provider: auto (local Ollama only, default), ollama, gemini, "
        "openrouter, anthropic. Naming a cloud provider opts in to sending data to it.",
    ),
    model: str = typer.Option(None, "--model", help="Model name for the provider"),
    allow_cloud: bool = typer.Option(
        False,
        "--allow-cloud",
        help="In auto mode, allow falling back to cloud providers with configured keys",
    ),
    no_redact: bool = typer.Option(
        False,
        "--no-redact",
        help="Do not mask likely secrets/emails in text sent to the LLM",
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
        project_root = str(Path.cwd())

        router = None
        if mode != "explain":
            settings = get_settings(
                provider=provider,
                model=model,
                allow_cloud=allow_cloud or None,
                redact=False if no_redact else None,
            )
            router = LLMRouter(settings, notify=_announce_provider)
            if not router.ready():
                _print_provider_problems(router)
                raise typer.Exit(code=2)
        else:
            console.print("[dim]Explain mode: context gathering only (no LLM)[/dim]")

        past = find_similar_issues(project_root)
        if past:
            console.print("[magenta]Similar issues detected from past runs:[/magenta]")
            for p in past[-2:]:
                console.print(
                    f"- {p.get('hypothesis', 'Unknown')} (confidence {p.get('confidence', 0.0)})"
                )

        state = AgentState(project_root=project_root)

        config = load_config(project_root)

        console.print("[bold green]OpsPilot initialized[/bold green]")
        console.print(f"[bold green]Project detected[/bold green]: {project_root}")
        console.print(f"Config loaded: {bool(config)}")

        # Capture build/runtime errors from various sources
        build_errors = None
        error_source = None

        if stdin_input:
            import select
            import sys

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
                console.print(
                    f"[cyan]Captured {len(build_errors)} bytes from stdin[/cyan]"
                )
            else:
                console.print(
                    "[yellow]Warning: --stdin specified but no input received[/yellow]"
                )

        elif error_input:
            build_errors = error_input
            error_source = "cli"
            console.print(
                f"[cyan]Using error input from --error flag ({len(build_errors)} bytes)[/cyan]"
            )

        elif build_cmd:
            import shlex
            import subprocess

            console.print(f"[cyan]Running build command: {build_cmd}[/cyan]")
            try:
                cmd_args = shlex.split(build_cmd)
                result = subprocess.run(
                    cmd_args,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=BUILD_CMD_TIMEOUT,
                    cwd=project_root,
                )
                # Capture both stdout and stderr
                build_errors = result.stdout + result.stderr
                error_source = "build_cmd"
                if result.returncode != 0:
                    console.print(
                        f"[yellow]Build command failed (exit code {result.returncode})[/yellow]"
                    )
                else:
                    console.print("[green]Build command completed[/green]")
            except subprocess.TimeoutExpired:
                console.print(
                    f"[red]Build command timed out after {BUILD_CMD_TIMEOUT}s[/red]"
                )
            except Exception as e:
                console.print(f"[red]Failed to run build command: {e}[/red]")

        # Fetch production logs if specified
        production_logs = None
        if log_source:
            console.print(f"[cyan]Fetching production logs from: {log_source}[/cyan]")
            production_logs = auto_detect_and_fetch(log_source)
            if production_logs:
                console.print(
                    f"[green]Successfully fetched {len(production_logs)} bytes of logs[/green]"
                )
            else:
                console.print(
                    "[yellow]Warning: Could not fetch production logs[/yellow]"
                )

        state.context = {
            "structure": scan_project_tree(project_root),
            "logs": production_logs if production_logs else read_logs(project_root),
            "env": read_env_names(project_root),
            "docker": find_docker_files(project_root),
            "dependencies": read_dependencies(project_root),
            "build_errors": build_errors,
        }
        console.print("[cyan]Context collected:[/cyan]")
        console.print(
            f"• Build errors: {bool(build_errors)} ({error_source or 'none'})"
        )
        console.print(
            f"• Logs found: {bool(state.context['logs'])} ({'production' if production_logs else 'local'})"
        )
        console.print(f"• Env vars: {len(state.context['env'])}")
        console.print(f"• Docker config: {bool(state.context['docker'])}")
        console.print(f"• Dependencies detected: {len(state.context['dependencies'])}")

        evidence = collect_evidence(state.context)
        state.evidence = evidence

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

                if evidence.get("timeline") and evidence["timeline"].get("first_seen"):
                    correlation = correlate_with_error_timeline(
                        deployment_info.get("commits", []),
                        evidence["timeline"]["first_seen"],
                    )

                    if correlation.get("correlation") == "strong":
                        console.print(
                            "\n[bold red]DEPLOYMENT CORRELATION DETECTED![/bold red]"
                        )
                        console.print(
                            f"[yellow]{correlation.get('reason', '')}[/yellow]"
                        )
                        console.print(
                            "\n[bold yellow]Suspicious Commits:[/bold yellow]"
                        )
                        for commit in correlation.get("suspicious_commits", [])[:3]:
                            console.print(
                                f"  [{commit.get('hash', 'unknown')}] {commit.get('message', '')}"
                            )
                            console.print(
                                f"    Time diff: {commit.get('time_diff_hours', '?')}h before error"
                            )
            else:
                console.print("[green]No recent deployments detected[/green]")

        # Display severity and error summary
        if evidence.get("severity"):
            severity = evidence["severity"]
            severity_color = {
                "P0": "bold red",
                "P1": "bold orange1",
                "P2": "bold yellow",
                "P3": "bold blue",
            }.get(severity, "white")

            console.print(
                f"\n[{severity_color}]SEVERITY: {severity}[/{severity_color}]"
            )

            if evidence.get("error_count"):
                console.print(f"[white]Total Errors: {evidence['error_count']}[/white]")

            if evidence.get("timeline"):
                timeline = evidence["timeline"]
                console.print(
                    f"[white]First Seen: {timeline.get('first_seen', 'unknown')}[/white]"
                )
                console.print(
                    f"[white]Occurrences: {timeline.get('total_occurrences', 0)}[/white]"
                )

        console.print("\n[cyan]Evidence collected:[/cyan]", evidence)

        if mode == "explain":
            result = {
                "project": project_root,
                "mode": "explain",
                "context": state.context,
                "evidence": evidence,
                "timestamp": datetime.now().isoformat(),
            }
            if output_file:
                save_report(output_file, result, console)
            if output_json:
                print(json.dumps(result, indent=2, default=str))
            console.print("\n[bold green]Context summary complete[/bold green]")
            console.print("[dim]Use --mode quick or --mode deep for LLM analysis[/dim]")
            return

        console.print("[cyan]Planner Agent reasoning...[/cyan]")
        if debug:
            console.print("[dim][debug] entering planner[/dim]")

        with console.status(
            "[cyan]Analyzing project context with LLM...[/cyan]", spinner="dots"
        ):
            plan_result = plan(state.context, router)
        if debug:
            console.print("[dim][debug] planner done[/dim]")

        state.hypothesis = plan_result.hypothesis
        state.confidence = plan_result.confidence
        state.checks_remaining = plan_result.required_checks

        console.print("[bold yellow]Hypothesis:[/bold yellow]", state.hypothesis)
        console.print("[bold yellow]Confidence:[/bold yellow]", state.confidence)

        verdict = None
        if state.hypothesis and evidence:
            if debug:
                console.print("[dim][debug] verifying[/dim]")
            console.print("[cyan]Verifying hypothesis...[/cyan]")
            verdict = verify(state.hypothesis, evidence, router).model_dump()
            if debug:
                console.print("[dim][debug] verification done[/dim]")

            console.print(
                "[bold yellow]Supported:[/bold yellow]", verdict.get("supported", False)
            )
            console.print(
                "[bold yellow]Confidence:[/bold yellow]", verdict.get("confidence", 0.0)
            )
            console.print(
                "[bold yellow]Reason:[/bold yellow]", verdict.get("reason", "N/A")
            )
        else:
            console.print("[yellow]Not enough evidence to verify hypothesis[/yellow]")

        # Use overridden confidence or default
        threshold = (
            min_confidence if min_confidence is not None else CONFIDENCE_THRESHOLD
        )

        if verdict and verdict.get("confidence", 0) >= threshold and state.hypothesis:
            if debug:
                console.print("[dim][debug] suggesting fixes[/dim]")
            console.print("[cyan]Generating safe fix suggestions (dry-run)...[/cyan]")

            suggestions = []

            if evidence.get("uses_redis") and "Timeout" in evidence.get(
                "log_errors", {}
            ):
                suggestions.append(redis_timeout_diff())
                suggestions.append(redis_pooling_diff())

            if not suggestions:
                fix_result = suggest(state.hypothesis, evidence, router)
                suggestions.extend(s.model_dump() for s in fix_result.suggestions)

            if suggestions:
                for s in suggestions:
                    console.print(f"\n[bold]File:[/bold] {s.get('file', 'unknown')}")
                    console.print(f"[dim]{s.get('rationale', '')}[/dim]")
                    console.print(s.get("diff", ""))

                # Generate and display remediation plan
                console.print("\n[bold cyan]Generating Remediation Plan...[/bold cyan]")
                remediation_plan = generate_remediation_plan(
                    state.hypothesis, evidence, suggestions
                )
                formatted_plan = format_remediation_output(remediation_plan)
                console.print(formatted_plan)
            else:
                console.print("[yellow]No safe suggestions generated.[/yellow]")
            if debug:
                console.print("[dim][debug] fixer done[/dim]")
        else:
            console.print("[yellow]Confidence too low — not generating fixes.[/yellow]")

        save_memory(
            {
                "project": project_root,
                "hypothesis": state.hypothesis,
                "confidence": verdict.get("confidence") if verdict else 0.0,
                "evidence": evidence,
            }
        )
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
            }
            if verdict
            else None,
            "timestamp": datetime.now().isoformat(),
        }

        # Save to output file if specified
        if output_file:
            save_report(output_file, result, console)

        if output_json:
            print(json.dumps(result, indent=2, default=str))
            return

        # Use overridden confidence or default
        threshold = (
            min_confidence if min_confidence is not None else CONFIDENCE_THRESHOLD
        )

        if not state.hypothesis or (state.confidence or 0) < threshold:
            console.print(
                f"[yellow]No confident diagnosis could be made. Evidence insufficient (threshold: {threshold}).[/yellow]"
            )
            return

    except KeyboardInterrupt:
        console.print("\n[yellow]Analysis interrupted by user[/yellow]")
        raise typer.Exit(code=130) from None
    except LogSourceError as e:
        console.print(f"[red]Log source error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except LLMError as e:
        console.print(f"[red]LLM error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except FileNotFoundError as e:
        console.print(f"[red]ERROR:[/red] File not found: {e}")
        if debug:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]FATAL ERROR:[/red] Analysis failed: {e}")
        if debug:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(code=1) from e


def _announce_provider(status: ProviderStatus) -> None:
    """Tell the user where data is about to be sent, before sending it."""
    style = "yellow" if status.is_cloud else "dim"
    console.print(f"[{style}]Using LLM: {status.label}[/{style}]")


def _print_provider_problems(router: LLMRouter) -> None:
    console.print("[red]ERROR:[/red] No permitted LLM provider is ready.")
    for status in router.statuses():
        console.print(f"  - {status.name}: {status.detail}")
    console.print(router.unavailable_hint())


@app.command()
def doctor(
    provider: str = typer.Option(None, "--provider", help="Provider to check"),
    model: str = typer.Option(None, "--model", help="Model to check"),
    allow_cloud: bool = typer.Option(
        False, "--allow-cloud", help="Include cloud providers in auto mode"
    ),
):
    """Check LLM provider configuration and connectivity."""
    from opspilot.llm import PROVIDERS, make_session, permitted_provider_names

    settings = get_settings(
        provider=provider, model=model, allow_cloud=allow_cloud or None
    )
    config_file = user_config_file()
    found = "found" if config_file.is_file() else "not found, using defaults"
    console.print(f"OpsPilot {VERSION}")
    console.print(f"Config file: {config_file} ({found})")
    console.print(f"Provider setting: {settings.provider}")
    console.print(f"Cloud fallback allowed: {settings.allow_cloud}")
    permitted = permitted_provider_names(settings)
    session = make_session()
    any_ready = False
    console.print("")
    console.print("Providers:")
    for name, cls in PROVIDERS.items():
        status = cls(settings, session).status()
        allowed = name in permitted
        any_ready = any_ready or (allowed and status.ready)
        mark = "[green]ready[/green]" if status.ready else "[red]not ready[/red]"
        use = "will be used" if allowed else "not permitted by current settings"
        console.print(f"  {status.label}: {mark}, {use}")
        console.print(f"      {status.detail}")
    console.print("")
    if not any_ready:
        console.print("[red]No permitted provider is ready.[/red]")
        raise typer.Exit(code=2)
    console.print("[green]OK[/green]: at least one permitted provider is ready.")
