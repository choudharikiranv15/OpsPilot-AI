# Architecture

OpsPilot is a single-process Python CLI. A run is a straight pipeline; there are no background services, databases or autonomous agents.

```
inputs ──► facts (deterministic) ──► diagnosis (LLM, must cite facts) ──► dry-run patches (LLM, validated)
                                            │
                                    AnalysisResult ──► terminal / --json / report
```

## Modules

| Module | Responsibility |
|---|---|
| `cli.py` | Typer commands (`analyze`, `doctor`, deprecated `troubleshoot`). Parses flags, reads `--stdin`/`--build-cmd`, prints. stdout carries only results; stderr carries progress and errors. |
| `pipeline.py` | `run_analysis(options, router)`: orchestrates one run and returns an `AnalysisResult`. Free of CLI concerns, so it is testable directly. |
| `models.py` | Pydantic models (`Fact`, `Hypothesis`, `Diagnosis`, `Suggestion`, `AnalysisResult`). This is also the `--json` schema. |
| `evidence.py` | Builds numbered facts (`F1`...) from build output, logs, stack frames, undefined env vars and git commits. No AI. |
| `context/` | Readers: `logs.py` (bounded discovery and tail reads), `production_logs.py` (`--log-source`: file, URL, S3, k8s, CloudWatch; validated and capped), `env.py` (env var names; reference scan), `deps.py` (dependency manifests), `docker.py` (file names), `deployment_history.py` (git). |
| `tools/` | `parse_build_errors` and regex `pattern_analysis` (severity heuristic, error statistics). |
| `agents/planner.py` | `diagnose()`: one structured LLM call; validates fact citations and ranks supported hypotheses first. |
| `agents/fixer.py` | `suggest()`: proposes patches only for files the evidence points to, using real file excerpts; checks each with `git apply --check`. Never writes. |
| `llm.py` | Providers (Ollama HTTP, Gemini, OpenRouter, Anthropic), the local-first `LLMRouter` (permitted providers, bounded retries, deadline), and `complete_structured()` (JSON extraction plus one repair). |
| `redact.py` | Masks likely secrets and emails in every prompt. |
| `settings.py` | Pydantic settings from flags, `OPSPILOT_*` env vars and `~/.config/opspilot/config.env`. |
| `memory.py` | Minimal local history (`~/.opspilot_memory.json`) for "seen before" hints; atomic, capped, corruption-tolerant. |
| `proc.py` | `run_bounded()`: shell-free subprocesses with streamed, tail-capped output and hard timeouts. |
| `render.py` | Terminal, Markdown, text and JSON rendering. Untrusted text is never interpreted as markup. |

## Key design decisions

- **Facts before opinions.** The LLM only reasons over numbered facts; citations are checked in code. This makes answers traceable and exposes guesses.
- **One diagnosis call.** The earlier separate planner and verifier LLM calls are replaced by one structured call plus deterministic citation checks. This is faster on local models and avoids two models disagreeing.
- **Local first, explicit egress.** `permitted_provider_names()` is the single place that decides where data may go.
- **Dry run only.** Patches are text. Validation uses `git apply --check` with `GIT_CEILING_DIRECTORIES`, so git cannot pick up an enclosing repository.
- **Everything bounded.** Input bytes, file counts, scan depth, fact counts, prompt size, retries and wall-clock time all have limits.

## Testing

`tests/` runs without network or Ollama. `tests/test_llm.py` provides `FakeSession`, a fake HTTP layer for providers, and `tests/test_cli_e2e.py` drives the real CLI with it. `scripts/ci_smoke_test.py` installs the built wheel into a fresh virtualenv and runs the CLI, which catches packaging problems that an editable install hides.
