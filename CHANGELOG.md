# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/). While the version is 0.x, minor releases may contain breaking changes.

## [Unreleased] - 0.2.0

A substantial rework based on an end-to-end audit (`OPSPILOT_AUDIT_REPORT.md`). Focus: correctness, privacy, and honest output.

### Breaking changes

- **Local-only by default.** OpsPilot no longer falls back from Ollama to cloud providers on its own. Use `--provider gemini|anthropic|openrouter` or `--allow-cloud`.
- **Configuration moved.** OpsPilot no longer loads the analysed project's `.env` (or any `.env` found by searching upwards) into its own environment. Put API keys in your shell environment or in `~/.config/opspilot/config.env`. See `config.env.example`.
- Default Ollama model is now `llama3.2`, called through Ollama's HTTP API. Missing models are reported with the `ollama pull` command instead of being downloaded implicitly.
- The HuggingFace provider was removed (its endpoint was retired). OpenRouter now requires `OPSPILOT_OPENROUTER_MODEL`.
- Output format changed: facts, hypotheses with citations, and dry-run patches. `--json` output has a new schema (`schema_version: "1"`).
- Automatic log discovery reads only `*.log` files; root-level `*.txt`/`*.jsonl` files are no longer treated as logs.
- `cw://` sources use `cw://GROUP::STREAM` (the old `cw://group/stream` still works when the group has no `/`).
- `opspilot troubleshoot` is deprecated (hidden). Its checks are part of `analyze`, and it now runs `analyze --no-llm`.
- `--mode deep` is deprecated (it was always identical to `quick`); `--mode explain` is replaced by `--no-llm`.
- The incident history file now stores only minimal fields. Older entries are slimmed automatically.
- Python 3.11+ is required.

### Added

- Deterministic, numbered facts (`F1`, `F2`, ...) from logs, build output, stack frames, undefined environment variables, and optional git history.
- Diagnosis hypotheses must cite facts; citations are validated, and unsupported hypotheses are labelled as guesses.
- Dry-run patches only for files the evidence points to, each checked with `git apply --check`.
- `opspilot doctor` shows configuration and provider readiness.
- `--provider`, `--model`, `--allow-cloud`, `--no-llm`, `--no-fix`, `--no-redact`; `--log-source` is repeatable.
- Redaction of likely secrets and emails before any text is sent to a model.
- Anthropic provider support.
- `python -m opspilot`.
- Documentation: privacy, configuration, troubleshooting, security policy, contributing guide.

### Fixed

- A clean install of the development branch failed with `ModuleNotFoundError: requests`.
- `opspilot troubleshoot` crashed (`TypeError`) and, when patched, stopped early whenever history existed.
- `.env` values were printed and saved in `--mode explain` output and reports.
- `--json` output was not valid JSON (status text was printed to stdout).
- Reports always had an empty `suggestions` list and showed an unverified confidence value.
- Log lines or model output containing `[...]` could crash the CLI or inject terminal hyperlinks.
- `--build-cmd` failed on Windows for `npm`/`ng` (`.cmd` shims) and with backslash paths, and discarded all output on timeout.
- `--stdin` ignored input that arrived after 0.1 s on Linux/macOS.
- A corrupt history file made every run fail.
- Canned Redis diffs were suggested for projects that don't contain the files they patch.
- Retries no longer apply to permanent errors (e.g. invalid API key), and every run has an overall time budget.
- Remote log sources are size-capped and their identifiers validated before being passed to `kubectl`/`aws`.
- Cargo inline-table versions, Gradle Kotlin-DSL dependencies, and files in a repository's first commit are now parsed correctly.

### Removed

- Unused modules: async provider stack, graph engine, Redis memory backend, mitigation playbooks, duplicate logging, runbook matcher, `.opspilot.json` loader.
- Unused optional extras (`redis`, `aws`, `k8s`) and the `httpx`/`structlog` dependencies.

### Project

- One CI workflow: lint, test matrix (Linux/macOS/Windows × Python 3.11-3.13), clean-wheel install smoke tests, security scans (gitleaks, pip-audit, bandit), and tag-triggered publishing via PyPI Trusted Publishing.
- Test suite grew from 58 to 150+ tests; coverage from 21% to about 89%.

## [0.1.0] - [0.1.6] - 2026-02-03 to 2026-02-05

Initial PyPI releases of `opspilot-ai`: the `analyze` command with planner, verifier and fixer LLM agents, multi-provider fallback (Ollama, Gemini, OpenRouter, HuggingFace), production log fetching, deployment correlation, and severity classification.

[Unreleased]: https://github.com/choudharikiranv15/OpsPilot-AI/commits/main
