"""OpsPilot command-line interface.

stdout carries only the result (human report, or JSON with --json);
progress, warnings and errors go to stderr.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

if sys.platform == "win32":  # make Unicode output safe on legacy Windows consoles
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError):
            _stream.reconfigure(encoding="utf-8", errors="replace")

from opspilot import llm
from opspilot.constants import CONFIDENCE_THRESHOLD, VERSION
from opspilot.context.production_logs import LogSourceError
from opspilot.exceptions import LLMError
from opspilot.llm import (
    PROVIDERS,
    LLMRouter,
    ProviderStatus,
    permitted_provider_names,
)
from opspilot.pipeline import AnalyzeOptions, run_analysis
from opspilot.proc import DEFAULT_MAX_BYTES, run_bounded, split_command, tail_bytes
from opspilot.render import render_json, render_terminal, save_report
from opspilot.settings import get_settings, user_config_file

app = typer.Typer(
    help="OpsPilot: local-first AI diagnosis of build and runtime errors.",
    no_args_is_help=True,
)
out = Console()
err = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        out.print(f"OpsPilot version {VERSION}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """OpsPilot command-line interface."""


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        stream=sys.stderr,
        format="opspilot %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def _announce_provider(status: ProviderStatus) -> None:
    """Say where data is about to be sent, before sending it."""
    style = "yellow" if status.is_cloud else "dim"
    err.print(f"[{style}]Using LLM: {escape(status.label)}[/{style}]")


def _fail(message: str, code: int = 1) -> typer.Exit:
    err.print(f"[red]Error:[/red] {escape(message)}")
    return typer.Exit(code=code)


def _read_stdin() -> str:
    if sys.stdin is None or sys.stdin.isatty():
        raise _fail(
            "--stdin expects piped input, e.g.  "
            "npm run build 2>&1 | opspilot analyze --stdin",
            2,
        )
    stream = getattr(sys.stdin, "buffer", None)
    if stream is not None:
        data = tail_bytes(iter(lambda: stream.read(64 * 1024), b""), DEFAULT_MAX_BYTES)
        return data.decode("utf-8", errors="replace")
    return sys.stdin.read()[-DEFAULT_MAX_BYTES:]


def _run_build_command(command: str, cwd: str, timeout: int) -> str:
    try:
        argv = split_command(command)
    except ValueError as e:
        raise _fail(f"Invalid --build-cmd: {e}", 2) from e
    err.print(f"[dim]Running build command: {escape(command)}[/dim]")
    try:
        result = run_bounded(argv, timeout=timeout, cwd=cwd, merge_stderr=True)
    except FileNotFoundError:
        raise _fail(f"Command not found: {argv[0]}") from None
    except OSError as e:
        raise _fail(f"Could not run build command: {e}") from e
    if result.timed_out:
        err.print(
            f"[yellow]Build command did not finish within {timeout}s; analysing the "
            "output captured so far. Long-running commands such as dev servers are "
            "not suitable for --build-cmd (see OPSPILOT_BUILD_TIMEOUT).[/yellow]"
        )
    elif result.returncode == 0:
        err.print("[dim]Build command succeeded.[/dim]")
    else:
        err.print(f"[dim]Build command exited with code {result.returncode}.[/dim]")
    return result.stdout


def _execute(
    *,
    use_llm: bool,
    output_json: bool,
    verbose: bool,
    debug: bool,
    log_sources: list[str],
    error_input: str | None,
    stdin_input: bool,
    build_cmd: str | None,
    since_hours: int | None,
    output_file: str | None,
    min_confidence: float | None,
    provider: str | None,
    model: str | None,
    allow_cloud: bool,
    no_redact: bool,
    no_fix: bool,
) -> None:
    _configure_logging(debug)
    project_root = str(Path.cwd())
    settings = get_settings(
        provider=provider,
        model=model,
        allow_cloud=allow_cloud or None,
        redact=False if no_redact else None,
    )

    if sum(bool(x) for x in (error_input, stdin_input, build_cmd)) > 1:
        raise _fail("Use only one of --error, --stdin and --build-cmd.", 2)

    router = None
    if use_llm:
        router = LLMRouter(settings, notify=_announce_provider)
        if not router.ready():
            err.print("[red]Error:[/red] no permitted LLM provider is ready.")
            for status in router.statuses():
                err.print(f"  - {status.name}: {escape(status.detail)}")
            err.print(escape(router.unavailable_hint()))
            err.print(
                "[dim]Use --no-llm to see the extracted facts without an LLM.[/dim]"
            )
            raise typer.Exit(code=2)

    build_output, build_source = None, "build output"
    if stdin_input:
        build_output, build_source = _read_stdin(), "stdin"
    elif error_input:
        build_output, build_source = error_input, "--error text"
    elif build_cmd:
        build_output = _run_build_command(
            build_cmd, project_root, settings.build_timeout
        )
        build_source = "build command output"

    options = AnalyzeOptions(
        project_root=project_root,
        use_llm=use_llm,
        build_output=build_output,
        build_source=build_source,
        log_sources=log_sources,
        since_hours=since_hours,
        min_confidence=(
            min_confidence if min_confidence is not None else CONFIDENCE_THRESHOLD
        ),
        suggest_fixes=not no_fix,
    )
    try:
        with err.status("Analysing...", spinner="dots") as status:
            result = run_analysis(
                options, router, progress=lambda msg: status.update(f"{msg}...")
            )
    except LogSourceError as e:
        raise _fail(f"Log source error: {e}") from e
    except LLMError as e:
        raise _fail(f"LLM error: {e}") from e

    if output_file:
        try:
            saved = save_report(output_file, result)
        except OSError as e:
            raise _fail(f"Could not write report: {e}") from e
        err.print(f"[green]Report saved to {escape(saved)}[/green]")
    if output_json:
        sys.stdout.write(render_json(result) + "\n")
        sys.stdout.flush()
    else:
        render_terminal(result, out, verbose=verbose)


@app.command()
def analyze(
    error_input: str = typer.Option(
        None,
        "--error",
        "-e",
        help="Error text to analyse (paste a stack trace or build error).",
    ),
    stdin_input: bool = typer.Option(
        False,
        "--stdin",
        help="Read error output from a pipe:  cmd 2>&1 | opspilot analyze --stdin",
    ),
    build_cmd: str = typer.Option(
        None,
        "--build-cmd",
        help="Run a build/test command (no shell) and analyse its output, "
        "e.g. 'npm run build'.",
    ),
    log_source: list[str] = typer.Option(
        None,
        "--log-source",
        help="Log to analyse instead of auto-discovered *.log files: file path, "
        "https:// URL, s3://bucket/key, k8s://ns/pod[/container], "
        "cw://GROUP::STREAM. Repeatable.",
    ),
    deployment_analysis: bool = typer.Option(
        False, "--deployment-analysis", help="Include recent git commits as evidence."
    ),
    since_hours: int = typer.Option(
        24, "--since-hours", min=1, help="Look-back window for --deployment-analysis."
    ),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Only extract facts; do not call any LLM."
    ),
    mode: str = typer.Option(
        "quick",
        "--mode",
        hidden=True,
        help="quick (default) or explain (same as --no-llm).",
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        help="auto (default: local Ollama only), ollama, gemini, openrouter, "
        "anthropic. Naming a cloud provider opts in to sending data to it.",
    ),
    model: str = typer.Option(None, "--model", help="Model for the provider."),
    allow_cloud: bool = typer.Option(
        False,
        "--allow-cloud",
        help="In auto mode, fall back to cloud providers that have keys.",
    ),
    no_redact: bool = typer.Option(
        False,
        "--no-redact",
        help="Do not mask likely secrets/emails in text sent to the LLM.",
    ),
    no_fix: bool = typer.Option(False, "--no-fix", help="Do not propose patches."),
    min_confidence: float = typer.Option(
        None,
        "--min-confidence",
        min=0.0,
        max=1.0,
        help="Model confidence needed before proposing patches "
        f"(default {CONFIDENCE_THRESHOLD}).",
    ),
    output_file: str = typer.Option(
        None, "--output", "-o", help="Also save a report (.md, .json, or text)."
    ),
    output_json: bool = typer.Option(
        False, "--json", help="Print JSON only (to stdout)."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show all extracted facts."
    ),
    debug: bool = typer.Option(False, "--debug", help="Debug logging to stderr."),
) -> None:
    """
    Diagnose why the project in the current directory is failing.

    Examples:

      npm run build 2>&1 | opspilot analyze --stdin

      opspilot analyze --error "ModuleNotFoundError: No module named 'redis'"

      opspilot analyze --build-cmd "pytest -x"

      opspilot analyze --log-source /var/log/myapp/error.log -o report.md

      opspilot analyze --no-llm       # facts only, nothing is sent anywhere
    """
    if mode not in ("quick", "deep", "explain"):
        raise typer.BadParameter("--mode must be quick or explain")
    if mode == "deep":
        err.print("[yellow]--mode deep is deprecated and behaves like quick.[/yellow]")
    _execute(
        use_llm=not (no_llm or mode == "explain"),
        output_json=output_json,
        verbose=verbose,
        debug=debug,
        log_sources=list(log_source or []),
        error_input=error_input,
        stdin_input=stdin_input,
        build_cmd=build_cmd,
        since_hours=since_hours if deployment_analysis else None,
        output_file=output_file,
        min_confidence=min_confidence,
        provider=provider,
        model=model,
        allow_cloud=allow_cloud,
        no_redact=no_redact,
        no_fix=no_fix,
    )


@app.command(hidden=True, deprecated=True)
def troubleshoot(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Deprecated: use 'opspilot analyze' (or 'opspilot analyze --no-llm')."""
    err.print(
        "[yellow]'troubleshoot' is deprecated; its checks are now part of "
        "'analyze'. Running 'opspilot analyze --no-llm --deployment-analysis'.[/yellow]"
    )
    _execute(
        use_llm=False,
        output_json=output_json,
        verbose=verbose,
        debug=False,
        log_sources=[],
        error_input=None,
        stdin_input=False,
        build_cmd=None,
        since_hours=48,
        output_file=None,
        min_confidence=None,
        provider=None,
        model=None,
        allow_cloud=False,
        no_redact=False,
        no_fix=True,
    )


@app.command()
def doctor(
    provider: str = typer.Option(None, "--provider", help="Provider to check."),
    model: str = typer.Option(None, "--model", help="Model to check."),
    allow_cloud: bool = typer.Option(
        False, "--allow-cloud", help="Include cloud providers in auto mode."
    ),
) -> None:
    """Check LLM provider configuration and connectivity."""
    settings = get_settings(
        provider=provider, model=model, allow_cloud=allow_cloud or None
    )
    config_file = user_config_file()
    found = "found" if config_file.is_file() else "not found, using defaults"
    out.print(f"OpsPilot {VERSION}")
    out.print(f"Config file: {escape(str(config_file))} ({found})")
    out.print(f"Provider setting: {settings.provider}")
    out.print(f"Cloud fallback allowed: {settings.allow_cloud}")
    out.print(f"Redaction before sending: {settings.redact}")
    permitted = permitted_provider_names(settings)
    session = llm.make_session()
    any_ready = False
    out.print()
    out.print("Providers:")
    for name, cls in PROVIDERS.items():
        status = cls(settings, session).status()
        allowed = name in permitted
        any_ready = any_ready or (allowed and status.ready)
        mark = "[green]ready[/green]" if status.ready else "[red]not ready[/red]"
        use = "will be used" if allowed else "not permitted by current settings"
        out.print(f"  {escape(status.label)}: {mark}, {use}")
        out.print(f"      {escape(status.detail)}")
    out.print()
    if not any_ready:
        out.print("[red]No permitted provider is ready.[/red]")
        raise typer.Exit(code=2)
    out.print("[green]OK[/green]: at least one permitted provider is ready.")
