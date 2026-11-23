"""The analysis pipeline, independent of the CLI (so it can be tested directly).

inputs -> numbered facts (deterministic) -> diagnosis (LLM, must cite facts)
       -> optional dry-run fix suggestions (validated) -> AnalysisResult
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from opspilot.agents.fixer import suggest
from opspilot.agents.planner import diagnose
from opspilot.constants import CONFIDENCE_THRESHOLD, VERSION
from opspilot.context.deployment_history import get_changed_files, get_recent_commits
from opspilot.context.deps import read_dependencies
from opspilot.context.docker import find_docker_files
from opspilot.context.env import find_undefined_env_vars, read_env_names
from opspilot.context.logs import read_logs
from opspilot.context.production_logs import auto_detect_and_fetch
from opspilot.evidence import build_facts
from opspilot.llm import LLMRouter
from opspilot.memory import find_similar_issues, save_memory
from opspilot.models import AnalysisResult, LLMUsage
from opspilot.tools import collect_evidence

log = logging.getLogger("opspilot.pipeline")

Progress = Callable[[str], None]


@dataclass
class AnalyzeOptions:
    project_root: str
    use_llm: bool = True
    build_output: str | None = None
    build_source: str = "build output"
    log_sources: list[str] = field(default_factory=list)
    since_hours: int | None = None
    min_confidence: float = CONFIDENCE_THRESHOLD
    suggest_fixes: bool = True


def run_analysis(
    options: AnalyzeOptions,
    router: LLMRouter | None,
    progress: Progress = lambda _msg: None,
) -> AnalysisResult:
    """Run the full analysis. Raises LogSourceError / LLMError on failures."""
    started = time.monotonic()
    root = str(Path(options.project_root).resolve())
    warnings: list[str] = []
    inputs: list[str] = []

    if options.build_output:
        inputs.append(options.build_source)

    progress("Reading logs")
    if options.log_sources:
        sections = []
        for source in options.log_sources:
            sections.append(f"=== {source} ===\n{auto_detect_and_fetch(source)}")
            inputs.append(source)
        logs = "\n\n".join(sections)
    else:
        logs = read_logs(root)
        if logs:
            inputs.append("local *.log files")

    progress("Scanning project")
    undefined_env = find_undefined_env_vars(root)
    commits = None
    if options.since_hours:
        commits = get_recent_commits(root, options.since_hours)
        for commit in commits[:5]:
            commit["files"] = get_changed_files(root, commit["hash"])
        inputs.append(f"git history (last {options.since_hours}h)")

    facts = build_facts(
        root,
        build_output=options.build_output,
        build_source=options.build_source,
        logs=logs,
        log_source=None,
        undefined_env=undefined_env,
        commits=commits,
    )
    evidence = collect_evidence({"logs": logs, "build_errors": options.build_output})
    result = AnalysisResult(
        opspilot_version=VERSION,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        project=root,
        mode="diagnose" if options.use_llm else "facts_only",
        inputs=inputs,
        severity=evidence.get("severity"),
        facts=facts,
        seen_before=find_similar_issues(root, evidence) if evidence else [],
    )

    if not any(f.kind in ("build_error", "log_error") for f in facts):
        warnings.append(
            "No error output was found. Pass the failing output with --error, "
            "--stdin, --build-cmd or --log-source."
        )

    if options.use_llm and router is not None and facts:
        progress("Diagnosing with the LLM")
        diagnosis = diagnose(facts, project_summary(root), router)
        result.diagnosis = diagnosis
        top = diagnosis.hypotheses[0] if diagnosis.hypotheses else None
        if top and not top.supported:
            warnings.append(
                "The model's top hypothesis did not cite any extracted fact; "
                "treat it as a guess."
            )
        if (
            options.suggest_fixes
            and top is not None
            and top.supported
            and top.confidence >= options.min_confidence
        ):
            progress("Proposing dry-run fixes")
            suggestions, dropped = suggest(root, facts, top, router)
            result.suggestions = suggestions
            if dropped:
                warnings.append(
                    f"{dropped} suggested change(s) referred to files outside the "
                    "evidence and were discarded."
                )
        save_memory(root, top.cause if top else None, evidence)

    if router is not None and router.active is not None:
        result.llm = LLMUsage(
            provider=router.active.name,
            model=router.active.model,
            location="cloud" if router.active.is_cloud else "local",
            requests=router.request_count,
            redactions=router.redaction_count,
        )
    result.warnings = warnings
    result.elapsed_seconds = round(time.monotonic() - started, 1)
    return result


def project_summary(project_root: str) -> dict:
    """Small, non-sensitive project description for the diagnosis prompt."""
    root = Path(project_root)
    try:
        top_level = sorted(
            p.name + ("/" if p.is_dir() else "")
            for p in root.iterdir()
            if not p.name.startswith(".")
        )[:40]
    except OSError:
        top_level = []
    return {
        "top_level_entries": top_level,
        "dependencies": read_dependencies(project_root)[:40],
        "docker_files": find_docker_files(project_root),
        "env_var_names_defined": read_env_names(project_root)[:40],
    }
