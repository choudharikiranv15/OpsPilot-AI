"""Rendering of analysis results: terminal, Markdown, plain text, JSON.

All text that comes from logs, files or the LLM is printed through Rich
``Text`` objects or ``escape()`` so it can never be interpreted as markup.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.text import Text

from opspilot.models import AnalysisResult, Fact

DEFAULT_FACT_LIMIT = 12
DISCLAIMER = (
    "Hypotheses, next steps and patches are AI-generated from your logs and files. "
    "Verify before acting. OpsPilot never changes your files."
)
_CHECK_LABEL = {
    "applies": "patch applies cleanly (git apply --check)",
    "does_not_apply": "patch does NOT apply to the current file; treat as a sketch",
    "not_checked": "patch not checked (git not available)",
}


def _fact_line(fact: Fact) -> Text:
    line = Text()
    line.append(f"{fact.id:>4} ", style="bold cyan")
    tag = fact.kind + (f" x{fact.count}" if fact.count > 1 else "")
    line.append(f"[{tag}] ", style="dim")
    line.append(f"{fact.source}: ", style="dim")
    line.append(fact.text)
    return line


def render_terminal(
    result: AnalysisResult, console: Console, verbose: bool = False
) -> None:
    """Human-readable report (stdout)."""
    console.print(Text(f"OpsPilot analysis of {result.project}", style="bold"))
    if result.inputs:
        console.print(Text("Inputs: " + ", ".join(result.inputs), style="dim"))
    if result.severity:
        console.print(
            Text(f"Severity estimate (heuristic): {result.severity}", style="dim")
        )

    console.print()
    console.print("[bold]Observed facts[/bold] [dim](extracted directly, no AI)[/dim]")
    facts = result.facts if verbose else result.facts[:DEFAULT_FACT_LIMIT]
    if not facts:
        console.print("  [dim]none[/dim]")
    for fact in facts:
        console.print(_fact_line(fact))
    hidden = len(result.facts) - len(facts)
    if hidden > 0:
        console.print(f"  [dim]... {hidden} more (use --verbose)[/dim]")

    if result.seen_before:
        console.print()
        console.print("[bold]Seen before in this project[/bold]")
        for past in result.seen_before:
            console.print(
                Text(
                    f"  {past.get('timestamp') or 'earlier run'}: {past.get('hypothesis')}",
                    style="magenta",
                )
            )

    diagnosis = result.diagnosis
    if diagnosis is not None:
        console.print()
        console.print("[bold]Diagnosis[/bold] [dim](AI-generated)[/dim]")
        if diagnosis.summary:
            console.print(Text(diagnosis.summary))
        if not diagnosis.hypotheses:
            console.print("  [dim]The model did not propose a hypothesis.[/dim]")
        for i, h in enumerate(diagnosis.hypotheses, 1):
            line = Text(f"  {i}. ", style="bold")
            line.append(h.cause)
            line.append(
                f"  ({h.category}, model confidence {h.confidence:.2f})", style="dim"
            )
            console.print(line)
            if h.supported:
                console.print(
                    Text("     cites " + ", ".join(h.evidence), style="green")
                )
            else:
                console.print(
                    Text(
                        "     cites no extracted fact: unverified guess", style="yellow"
                    )
                )
        if diagnosis.missing_information:
            console.print()
            console.print("[bold]Missing information[/bold]")
            for item in diagnosis.missing_information:
                console.print(Text(f"  - {item}"))
        if diagnosis.next_steps:
            console.print()
            console.print(
                "[bold]Suggested next checks[/bold] [dim](review before running)[/dim]"
            )
            for step in diagnosis.next_steps:
                console.print(Text(f"  - {step}"))

    # Patches that failed 'git apply --check' are usually invented code; only
    # show them on request (they remain in --json and saved reports).
    shown = [s for s in result.suggestions if verbose or s.check != "does_not_apply"]
    hidden_patches = len(result.suggestions) - len(shown)
    if shown:
        console.print()
        console.print("[bold]Dry-run patch suggestions[/bold] [dim](not applied)[/dim]")
        for s in shown:
            console.print(Text(f"  {s.file}", style="bold"))
            if s.rationale:
                console.print(Text(f"  {s.rationale}", style="dim"))
            style = "green" if s.check == "applies" else "yellow"
            console.print(Text(f"  {_CHECK_LABEL[s.check]}", style=style))
            console.print(Text(s.diff.rstrip()))
    if hidden_patches:
        console.print()
        console.print(
            f"[dim]{hidden_patches} proposed patch(es) did not apply to your files "
            "and are hidden (see --verbose, --json or -o report.md).[/dim]"
        )

    for warning in result.warnings:
        console.print(f"[yellow]Note:[/yellow] {escape(warning)}")

    console.print()
    footer = []
    if result.llm:
        footer.append(
            f"LLM: {result.llm.provider} ({result.llm.model}, {result.llm.location})"
        )
        footer.append(f"{result.llm.requests} request(s)")
        footer.append(f"{result.llm.redactions} value(s) redacted")
    elif result.mode == "facts_only":
        footer.append("facts only, no LLM used")
    footer.append(f"{result.elapsed_seconds:.1f}s")
    console.print(Text(" · ".join(footer), style="dim"))
    if result.mode == "diagnose":
        console.print(Text(DISCLAIMER, style="dim"))


def render_json(result: AnalysisResult) -> str:
    return json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False)


def render_markdown(result: AnalysisResult) -> str:
    lines = [
        "# OpsPilot Analysis Report",
        "",
        f"- **Project:** `{result.project}`",
        f"- **Generated:** {result.timestamp} (OpsPilot {result.opspilot_version})",
        f"- **Inputs:** {', '.join(result.inputs) or 'none'}",
    ]
    if result.severity:
        lines.append(f"- **Severity estimate (heuristic):** {result.severity}")
    if result.llm:
        lines.append(
            f"- **LLM:** {result.llm.provider} ({result.llm.model}, {result.llm.location}); "
            f"{result.llm.redactions} value(s) redacted before sending"
        )
    lines += [
        "",
        "## Observed facts",
        "",
        "Extracted directly from the inputs (no AI).",
        "",
    ]
    lines += [
        f"- **{f.id}** [{f.kind}{f' x{f.count}' if f.count > 1 else ''}] "
        f"`{f.source}`: {_md(f.text)}"
        for f in result.facts
    ] or ["_None._"]
    if result.diagnosis:
        d = result.diagnosis
        lines += ["", "## Diagnosis (AI-generated)", ""]
        if d.summary:
            lines += [_md(d.summary), ""]
        for i, h in enumerate(d.hypotheses, 1):
            cites = (
                ", ".join(h.evidence)
                if h.supported
                else "no extracted fact (unverified)"
            )
            lines.append(
                f"{i}. {_md(h.cause)} - _{h.category}, model confidence "
                f"{h.confidence:.2f}; cites {cites}_"
            )
        if d.missing_information:
            lines += ["", "### Missing information", ""]
            lines += [f"- {_md(x)}" for x in d.missing_information]
        if d.next_steps:
            lines += ["", "### Suggested next checks (review before running)", ""]
            lines += [f"- {_md(x)}" for x in d.next_steps]
    if result.suggestions:
        lines += ["", "## Dry-run patch suggestions (not applied)", ""]
        for s in result.suggestions:
            lines += [
                f"### `{s.file}`",
                "",
                _md(s.rationale),
                "",
                f"_{_CHECK_LABEL[s.check]}_",
                "",
                "```diff",
                s.diff.rstrip(),
                "```",
                "",
            ]
    if result.warnings:
        lines += ["", "## Notes", ""] + [f"- {_md(w)}" for w in result.warnings]
    lines += ["", "---", "", f"_{DISCLAIMER}_", ""]
    return "\n".join(lines)


def render_text(result: AnalysisResult) -> str:
    console = Console(record=True, width=100, color_system=None, file=open_null())
    render_terminal(result, console, verbose=True)
    return console.export_text()


def save_report(path: str, result: AnalysisResult) -> str:
    """Write a report; format by extension (.json, .md, otherwise text)."""
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix == ".json":
        content = render_json(result)
    elif suffix in (".md", ".markdown"):
        content = render_markdown(result)
    else:
        content = render_text(result)
    target.write_text(content, encoding="utf-8")
    return str(target)


def _md(text: str) -> str:
    """Neutralise characters that could break out of Markdown list items."""
    return text.replace("\r", " ").replace("\n", " ").replace("<", "&lt;")


def open_null():
    import io

    return io.StringIO()
