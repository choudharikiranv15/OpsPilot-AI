"""
Structured troubleshooting command following real SRE debugging patterns.
"""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from opspilot.workflow import TroubleshootingWorkflow

console = Console()


def troubleshoot_command(
    project_root: str | None = None, verbose: bool = False, output_json: bool = False
):
    """
    Execute structured troubleshooting workflow.

    Follows real SRE debugging patterns:
    1. Logs → What broke
    2. Recent Changes → When did it break
    3. Similar Incidents → Has this happened before
    4. Stack Trace → Where did it break
    5. Environment → Configuration issues
    6. Dependencies → Version conflicts
    7. Resources → System limits
    8. External Services → Third-party failures
    9. Root Cause → Hypothesis formation
    10. Remediation → Action plan
    """
    project_root = project_root or str(Path.cwd())

    console.print("\n[bold cyan]OpsPilot Troubleshooting Workflow[/bold cyan]")
    console.print(f"[dim]Project: {project_root}[/dim]\n")

    # Initialize workflow
    workflow = TroubleshootingWorkflow(project_root)

    # Execute with progress reporting
    with console.status("[cyan]Analyzing...") as status:
        # Phase 1: Logs
        status.update("[cyan]📋 Phase 1/10: Analyzing logs...")
        workflow.execute()

    # Display results in structured format
    if verbose:
        _display_detailed_results(workflow)
    else:
        _display_summary_results(workflow)

    if output_json:
        import json

        summary = workflow.get_summary()
        print(json.dumps(summary, indent=2, default=str))


def _display_summary_results(workflow: TroubleshootingWorkflow):
    """Display concise summary of findings."""
    context = workflow.context

    # Summary panel
    summary_text = f"""
[bold]Root Cause:[/bold] {context.root_cause_hypothesis or "Unknown"}
[bold]Confidence:[/bold] {context.confidence:.1%}
[bold]Severity:[/bold] {context.severity or "Unknown"}
[bold]Errors Found:[/bold] {context.error_count}
"""

    if context.similar_incidents:
        summary_text += f"\n[yellow]⚠ {len(context.similar_incidents)} similar past incidents found[/yellow]"

    console.print(
        Panel(summary_text, title="[bold green]Diagnosis", border_style="green")
    )

    # Key findings
    if context.error_count > 0:
        console.print("\n[bold cyan]Key Findings:[/bold cyan]")

        if context.missing_env_vars:
            console.print(
                f"  ⚠ Missing environment variables: {', '.join(context.missing_env_vars[:3])}"
            )

        if context.recent_commits:
            console.print(
                f"  📅 Recent changes: {len(context.recent_commits)} commits in last 48h"
            )

        if context.affected_files:
            console.print(
                f"  📁 Affected files: {', '.join(context.affected_files[:3])}"
            )

        if context.memory_errors:
            console.print("  💾 Memory errors detected")

        if context.timeout_errors:
            console.print("  ⏱️ Timeout errors detected")

        if context.connection_errors:
            console.print("  🔌 Connection errors detected")

    # Remediation steps
    if context.remediation_steps:
        console.print("\n[bold cyan]Recommended Actions:[/bold cyan]")
        for i, step in enumerate(context.remediation_steps[:5], 1):
            console.print(f"  {i}. {step}")

        if len(context.remediation_steps) > 5:
            console.print(
                f"  [dim]... and {len(context.remediation_steps) - 5} more[/dim]"
            )


def _display_detailed_results(workflow: TroubleshootingWorkflow):
    """Display detailed phase-by-phase results."""
    context = workflow.context

    # Phase results tree
    tree = Tree("[bold]Troubleshooting Workflow[/bold]")

    for phase, result in workflow.phase_results.items():
        phase_node = tree.add(
            f"[{'green' if result.confidence > 0.6 else 'yellow' if result.confidence > 0.3 else 'dim'}]"
            f"{phase.value.replace('_', ' ').title()} "
            f"(confidence: {result.confidence:.1%})[/]"
        )

        # Add findings
        for key, value in result.findings.items():
            phase_node.add(f"{key}: {value}")

        if result.reasoning:
            phase_node.add(f"[dim]→ {result.reasoning}[/dim]")

    console.print(tree)

    # Detailed evidence table
    console.print("\n[bold cyan]Evidence Collected:[/bold cyan]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Category", style="cyan")
    table.add_column("Finding", style="white")
    table.add_column("Count", justify="right", style="yellow")

    table.add_row("Errors", context.severity or "None", str(context.error_count))
    table.add_row("Recent Changes", "Commits", str(len(context.recent_commits)))
    table.add_row(
        "Similar Incidents", "Past occurrences", str(len(context.similar_incidents))
    )
    table.add_row(
        "Affected Files", "Files with errors", str(len(context.affected_files))
    )
    table.add_row("Missing Config", "Env variables", str(len(context.missing_env_vars)))
    table.add_row("Dependencies", "Packages", str(len(context.dependencies)))

    console.print(table)

    # Timeline
    if context.first_occurrence:
        console.print("\n[bold cyan]Timeline:[/bold cyan]")
        console.print(f"  First occurrence: {context.first_occurrence}")
        if context.last_occurrence:
            console.print(f"  Last occurrence: {context.last_occurrence}")

    # Root cause analysis
    console.print("\n[bold green]Root Cause Analysis:[/bold green]")
    console.print(f"  Hypothesis: {context.root_cause_hypothesis}")
    console.print(f"  Confidence: {context.confidence:.1%}")

    # Full remediation plan
    if context.remediation_steps:
        console.print(
            f"\n[bold cyan]Remediation Plan ({len(context.remediation_steps)} steps):[/bold cyan]"
        )
        for i, step in enumerate(context.remediation_steps, 1):
            console.print(f"  {i}. {step}")
