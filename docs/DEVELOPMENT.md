# Development

## Setup

```bash
git clone https://github.com/choudharikiranv15/OpsPilot-AI.git
cd OpsPilot-AI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Checks

```bash
ruff check . && ruff format --check .
pytest --cov=opspilot      # no network or Ollama needed; CI enforces the coverage gate
```

The tests use a fake HTTP session (`FakeSession` in `tests/test_llm.py`) and drive the real CLI with it (`tests/test_cli_e2e.py`). `scripts/ci_smoke_test.py` installs the built wheel into a fresh virtualenv, which catches packaging problems that an editable install hides. `tests/fixtures/sample_project/` holds a small project whose `.env` contains a fake canary secret.

## How it works

A run is a straight pipeline in a single process:

```
inputs -> facts (deterministic) -> diagnosis (LLM, must cite facts) -> dry-run patches (LLM, validated) -> report
```

| Module | Responsibility |
|---|---|
| `cli.py` | Typer commands (`analyze`, `doctor`, hidden deprecated `troubleshoot`). stdout carries only results; stderr carries progress and errors. |
| `pipeline.py` | `run_analysis()`: orchestrates one run and returns an `AnalysisResult` |
| `models.py` | Pydantic result models; also the `--json` schema |
| `evidence.py` | Numbered facts from build output, logs, stack frames, env vars and git |
| `context/` | Bounded readers: local logs, `--log-source`, `.env` names, dependency manifests, Docker files, git |
| `tools/` | Build-error parsing and log pattern statistics |
| `agents/planner.py` | One structured diagnosis call; validates citations |
| `agents/fixer.py` | Patches only for files the evidence points to; `git apply --check` |
| `llm.py` | Providers, the local-first router (retries, deadline), structured output |
| `redact.py` | Masks likely secrets in every prompt |
| `settings.py` | Settings from flags, `OPSPILOT_*` and `~/.config/opspilot/config.env` |
| `memory.py` | Small, atomic, capped history for "seen before" hints |
| `proc.py` | Shell-free subprocesses with capped output and timeouts |
| `render.py` | Terminal, Markdown, text and JSON output (untrusted text is never rendered as markup) |

## Rules for changes

- Model output is never executed and never written to the project.
- New destinations for data must be opt-in and documented in the README's Privacy section.
- Never collect secret values; add a canary test for new inputs.
- Treat log, file and model text as data: render it literally and delimit it in prompts.
- Every new input needs size, count and time limits.
- Update the README and `CHANGELOG.md` (`[Unreleased]`) in the same change.
- Commits use conventional prefixes (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`) and are authored by the maintainer. No bots and no attribution trailers.

## Evaluating diagnosis quality

`scripts/eval_diagnosis.py` runs the diagnosis on 12 realistic failures and reports schema validity, citation validity and category accuracy for any configured provider:

```bash
python scripts/eval_diagnosis.py                  # default model
python scripts/eval_diagnosis.py --model llama3.2
python scripts/eval_diagnosis.py --markdown results.md
```

Results from 2026-11-23 (local Ollama, Windows laptop, CPU):

| Model | Schema-valid | Cites a real fact | Category accuracy | Median time/case |
|---|---|---|---|---|
| `llama3.2` (3B) | 12/12 | 12/12 | 9/12 | ~8 s |
| `llama3` (8B) | 12/12 | 12/12 | 10-11/12 | ~18 s |

Twelve cases make this a regression check, not a benchmark. Run it before and after changing prompts or evidence extraction.

## Releasing

Releases are published to PyPI by GitHub Actions from `v*` tags, using PyPI Trusted Publishing (no stored token).

One-time setup:

1. On pypi.org, open project `opspilot-ai`, go to **Publishing**, and add a trusted publisher: repository `choudharikiranv15/OpsPilot-AI`, workflow `ci.yml`, environment `pypi`.
2. In GitHub, go to **Settings → Environments** and create `pypi`.
3. Delete any old `PYPI_API_TOKEN` repository secret.

Each release:

1. Confirm `main` is green in CI.
2. In `CHANGELOG.md`, rename `[Unreleased]` to the version and date. Set `version` in `pyproject.toml`.
3. Commit (`chore(release): X.Y.Z`), then tag and push:

   ```bash
   git tag -a vX.Y.Z -m "OpsPilot X.Y.Z"
   git push origin vX.Y.Z
   ```

4. CI runs all checks and publishes to PyPI. Create a GitHub Release from the tag, with the changelog section as notes.
5. Verify: `pipx install opspilot-ai==X.Y.Z && opspilot --version && opspilot doctor`.
6. Bump `pyproject.toml` to the next `.dev0` version.

PyPI never accepts the same version twice. Fix mistakes with a new patch release.
