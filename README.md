# OpsPilot

[![PyPI](https://img.shields.io/pypi/v/opspilot-ai.svg)](https://pypi.org/project/opspilot-ai/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/choudharikiranv15/OpsPilot-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/choudharikiranv15/OpsPilot-AI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**OpsPilot explains why your build or app is failing, using evidence from your own logs, and by default it never sends your code or logs off your machine.**

You point it at a failure: build output, a stack trace, or log files. OpsPilot:

1. **Extracts facts deterministically** (no AI): error lines, build errors, stack frames in your code, environment variables your code uses but your `.env` doesn't define, and optionally recent commits. Each fact gets an ID (`F1`, `F2`, ...).
2. **Asks a local LLM** (via [Ollama](https://ollama.com)) for up to three root-cause hypotheses, each of which **must cite the facts it relies on**. Citations are checked; hypotheses that cite nothing are marked as guesses.
3. **Optionally proposes dry-run patches** for files that the evidence points to, and checks each patch with `git apply --check`. **OpsPilot never modifies your files.**

> **Status: alpha (0.2.0 in development).** The `main` branch is a substantial rework of the 0.1.x releases on PyPI. See [CHANGELOG.md](CHANGELOG.md).

---

## Install

OpsPilot needs Python 3.11+ and is best installed with [pipx](https://pipx.pypa.io), which keeps it isolated from your projects:

```bash
pipx install opspilot-ai
```

Until 0.2.0 is published, install the development version from GitHub:

```bash
pipx install git+https://github.com/choudharikiranv15/OpsPilot-AI.git
```

## Set up a local model

1. Install Ollama from <https://ollama.com/download> and make sure it is running.
2. Pull a model. The default is `llama3.2` (about 2 GB):

   ```bash
   ollama pull llama3.2
   ```

3. Check the setup:

   ```bash
   opspilot doctor
   ```

Small models such as `llama3.2` (3B) work, but their diagnoses are noticeably weaker. On OpsPilot's 12-case evaluation, `llama3.2` picked the right root-cause category 9 times out of 12 and the 8B `llama3` 11 times, at about twice the latency ([docs/evaluation.md](docs/evaluation.md)). If your hardware allows, use a larger instruction-tuned model with `--model` or `OPSPILOT_OLLAMA_MODEL`. OpsPilot never downloads models for you; if the configured model is missing it tells you the `ollama pull` command.

Prefer a hosted model? See [Cloud providers](#cloud-providers-opt-in).

## Use it

Run OpsPilot from your project directory and give it the failure:

```bash
# Pipe a failing build or test run
npm run build 2>&1 | opspilot analyze --stdin
pytest -x 2>&1 | opspilot analyze --stdin

# Or let OpsPilot run the command (no shell; output is captured)
opspilot analyze --build-cmd "npm run build"

# Paste an error
opspilot analyze --error "ModuleNotFoundError: No module named 'redis'"

# Analyse logs (by default: *.log files in ./logs, ./log, ./var/log and the project root)
opspilot analyze
opspilot analyze --log-source /var/log/myapp/error.log

# Include recent git commits as evidence
opspilot analyze --deployment-analysis --since-hours 24

# Facts only: no LLM, nothing leaves your machine
opspilot analyze --no-llm

# Save a report, or get JSON for scripts and CI
opspilot analyze -o report.md
opspilot analyze --json > result.json
```

`--log-source` also accepts `https://` URLs, `s3://bucket/key` (needs the AWS CLI), `k8s://NAMESPACE/POD` or `k8s://NAMESPACE/POD/CONTAINER` (needs `kubectl`), and `cw://LOG_GROUP::LOG_STREAM` (needs the AWS CLI). All sources are capped at the most recent 5 MB.

### Example output

From the sample project in [`tests/fixtures/sample_project`](tests/fixtures/sample_project), using the default `llama3.2` model:

```text
Observed facts (extracted directly, no AI)
  F1 [log_error] logs/app.log: ERROR redis.exceptions.TimeoutError: Timeout reading from socket
  F2 [log_error] logs/app.log: ERROR GET /api/orders failed with status 503
  F5 [log_error] logs/app.log: ERROR psycopg2.OperationalError: connection refused to db:5432
  F7 [stack_frame] logs: Stack frame at app/main.py:42
  F8 [config] source code scan: Environment variables referenced in code but not defined
     in the project's .env files (they may still be set at runtime): DATABASE_URL (app/main.py)

Diagnosis (AI-generated)
Application is experiencing intermittent connection issues with Redis and PostgreSQL
  1. Resource exhaustion due to unhandled exceptions in the application
     (resource_exhaustion, model confidence 0.80)
     cites F1, F4

Dry-run patch suggestions (not applied)
  app/main.py
  patch does NOT apply to the current file; treat as a sketch

LLM: ollama (llama3.2, local) · 3 request(s) · 0 value(s) redacted · 36.2s
```

The summary is reasonable but the top hypothesis is weak, which is typical of a 3B model. The facts it cites are real, so you can check it quickly. More examples: [EXAMPLES.md](EXAMPLES.md).

### Reading the results

| Section | Produced by | How much to trust it |
|---|---|---|
| **Observed facts** | Deterministic parsing | Exactly what is in your inputs |
| **Diagnosis** | The LLM | A hypothesis. Check the cited facts. "Cites no extracted fact" means it is a guess. |
| **Suggested next checks** | The LLM | Read-only checks to confirm the cause. Review before running. |
| **Dry-run patches** | The LLM, then checked | Only for files the evidence points to. "applies cleanly" means `git apply --check` passed, not that the fix is correct. |

"Model confidence" is the model's own estimate, not a measured probability.

## Privacy

- **Local by default.** With no configuration, OpsPilot only talks to Ollama on `localhost`.
- **`.env` values are never read into OpsPilot's output or prompts**, only variable names. Docker files are reported by name only.
- **Redaction.** Likely secrets (API keys, tokens, passwords in `key=value` or URLs, private keys, emails) are masked in everything sent to a model, including the local one. Disable with `--no-redact`.
- **History.** OpsPilot keeps a small local history (`~/.opspilot_memory.json`: project path, time, hypothesis and an error fingerprint) to show "seen before" hints. Delete the file to clear it.

Details: [docs/privacy.md](docs/privacy.md).

## Cloud providers (opt in)

Gemini, Anthropic and OpenRouter are supported, but your logs are only sent to them when you opt in:

```bash
export GOOGLE_API_KEY=...              # or ANTHROPIC_API_KEY / OPENROUTER_API_KEY
opspilot analyze --provider gemini     # explicitly use this provider
opspilot analyze --allow-cloud         # local first, cloud only if Ollama fails
```

OpsPilot prints which provider and model it is about to use before it sends anything. OpenRouter also needs a model ID (`OPSPILOT_OPENROUTER_MODEL`). See [docs/configuration.md](docs/configuration.md).

## Commands

| Command | Purpose |
|---|---|
| `opspilot analyze` | Diagnose the failure in the current directory (`opspilot analyze --help` for all options) |
| `opspilot doctor` | Show configuration and whether each provider is ready |
| `opspilot --version` | Print the version |

Exit codes: `0` success, `1` error (bad log source, LLM failure, ...), `2` usage or setup problem (no ready provider, invalid options).

## Configuration

Settings come from command-line flags, `OPSPILOT_*` environment variables, or `~/.config/opspilot/config.env` (see [config.env.example](config.env.example)). OpsPilot does **not** read the `.env` file of the project you are analysing for its own settings. Full list: [docs/configuration.md](docs/configuration.md).

## Limitations

- Diagnosis quality depends heavily on the model; small local models make mistakes.
- Log parsing is heuristic and tuned for common formats (Python, Node/TypeScript, JVM, Go, Rust, nginx-style access logs).
- Remote log sources (S3, Kubernetes, CloudWatch) are lightly tested against real services.
- One project directory per run; there is no daemon, dashboard, or alerting integration.

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md). Start with `opspilot doctor`.

## Development

```bash
git clone https://github.com/choudharikiranv15/OpsPilot-AI.git
cd OpsPilot-AI
pip install -e ".[dev]"
pytest                      # unit and end-to-end tests (no network or Ollama needed)
ruff check . && ruff format --check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [ARCHITECTURE.md](ARCHITECTURE.md). Security issues: [SECURITY.md](SECURITY.md).

## License

MIT; see [LICENSE](LICENSE).
