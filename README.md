# OpsPilot

[![PyPI](https://img.shields.io/pypi/v/opspilot-ai.svg)](https://pypi.org/project/opspilot-ai/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/choudharikiranv15/OpsPilot-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/choudharikiranv15/OpsPilot-AI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**OpsPilot explains why your build or app is failing, using evidence from your own logs. By default your code and logs never leave your machine.**

You point it at a failure (build output, a stack trace, or log files), and OpsPilot:

1. **Extracts facts deterministically** (no AI): error lines, grouped compiler errors with counts and locations, stack frames in your code, environment variables your code uses but your `.env` doesn't define, and optionally recent commits. Each fact gets an ID (`F1`, `F2`, ...).
2. **Asks a local LLM** (via [Ollama](https://ollama.com)) for up to three root-cause hypotheses. Each one **must cite the facts it relies on**. Citations are checked, and a hypothesis that cites nothing is marked as a guess.
3. **Optionally proposes dry-run patches** for files the evidence points to, and checks each one with `git apply --check`. **OpsPilot never modifies your files.**

> **Status: alpha.** See [CHANGELOG.md](CHANGELOG.md).

## Install

OpsPilot needs Python 3.11+. Install it with [pipx](https://pipx.pypa.io), which keeps it isolated from your projects:

```bash
pipx install opspilot-ai
```

Until version 0.2.0 is published on PyPI, install the current version from GitHub instead:

```bash
pipx install git+https://github.com/choudharikiranv15/OpsPilot-AI.git
```

## Set up a local model

1. Install Ollama from <https://ollama.com/download> and make sure it is running.
2. Pull the default model, `llama3` (8B, about 4.7 GB):

   ```bash
   ollama pull llama3
   ```

3. Check the setup:

   ```bash
   opspilot doctor
   ```

OpsPilot never downloads models for you. If the configured model is missing, it tells you the `ollama pull` command. You can use another model with `--model` or `OPSPILOT_OLLAMA_MODEL`. Small models (3B and below) are faster but often vague or wrong: on our 12-case evaluation, `llama3.2` (3B) picked the right root-cause category 9/12 times and `llama3` (8B) 11/12 times. `opspilot doctor` warns you when a small model is configured.

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

`--log-source` also accepts `https://` URLs, `s3://bucket/key` (needs the AWS CLI), `k8s://NAMESPACE/POD` or `k8s://NAMESPACE/POD/CONTAINER` (needs `kubectl`), and `cw://LOG_GROUP::LOG_STREAM` (needs the AWS CLI). Every source is capped at the most recent 5 MB.

`--build-cmd` runs the command you give with your own permissions in the current directory, without a shell (no `&&`, pipes or `$VAR` expansion), and stops it after `OPSPILOT_BUILD_TIMEOUT` seconds. Long-running commands such as dev servers are not suitable; pipe a one-shot build into `--stdin` instead.

### Example

A service log with Redis timeouts, an HTTP 503 and a refused Postgres connection, using the default `llama3`. This is real output from [`tests/fixtures/sample_project`](tests/fixtures/sample_project):

```text
Observed facts (extracted directly, no AI)
  F1 [log_error] logs/app.log: ERROR redis.exceptions.TimeoutError: Timeout reading from socket
  F2 [log_error] logs/app.log: ERROR GET /api/orders failed with status 503
  F5 [log_error] logs/app.log: ERROR psycopg2.OperationalError: connection refused to db:5432
  F7 [stack_frame] logs: Stack frame at app/main.py:42
  F8 [config] source code scan: Environment variables referenced in code but not defined in the
     project's .env files (they may still be set at runtime): DATABASE_URL (app/main.py)

Diagnosis (AI-generated)
The application is experiencing timeouts and database connection errors, possibly due to issues
with Redis or PostgreSQL.
  1. Redis connection timeout  (resource_exhaustion, model confidence 0.80)
     cites F1, F4
  2. Database connection refused  (database, model confidence 0.60)
     cites F5
  3. Flask API endpoint failed with status 503  (code_bug, model confidence 0.40)
     cites F2

Suggested next checks (review before running)
  - Check Redis connection settings and monitor Redis metrics; Check PostgreSQL connection
    settings and query logs for any errors or slow queries

LLM: ollama (llama3, local) · 2 request(s) · 0 value(s) redacted · 55.1s
```

On a real TypeScript project with 140 compiler errors, the facts lead with `140 errors in 15 files; by code: TS1117 x106, ...; most affected files: src/i18n.ts (106)`, which points straight at the main problem.

### Reading the results

| Section | Produced by | How much to trust it |
|---|---|---|
| **Observed facts** | Deterministic parsing | Exactly what is in your inputs |
| **Diagnosis** | The LLM | A hypothesis. Check the cited facts. "Cites no extracted fact" means it is a guess. |
| **Suggested next checks** | The LLM | Read-only checks to confirm the cause. Review before running. |
| **Dry-run patches** | The LLM, then checked | Shown only if `git apply --check` passes; patches that don't apply are hidden unless you use `--verbose`. "Applies" doesn't mean "correct". |

"Model confidence" is the model's own estimate, not a measured probability. `--verbose` shows every extracted fact.

Exit codes: `0` success, `1` error (bad log source, LLM failure, ...), `2` usage or setup problem (no ready provider, invalid options).

## Privacy

| Setting | Where your data can go |
|---|---|
| Default | Only Ollama on `localhost`. If Ollama is unavailable, OpsPilot stops; it does **not** fall back to the cloud. |
| `--provider gemini` / `anthropic` / `openrouter` | Only that provider. Naming it is your opt-in. |
| `--allow-cloud` | Ollama first, then cloud providers that have an API key. |
| `--no-llm` | Nowhere. |

- **Secrets:** `.env` files are read for variable **names only**; values never reach output, reports or prompts. Docker files are reported by name only. Before anything is sent to a model, likely secrets (API keys, tokens, passwords in `key=value` pairs or URLs, private keys, emails) are masked, and the output reports how many. Disable this with `--no-redact`.
- **What is sent:** the numbered facts, a small project summary (top-level file names, dependency list, `.env` variable names) and, when proposing a patch, short excerpts of the files the evidence points to. OpsPilot prints the provider and model before it sends anything.
- **What is stored:** `~/.opspilot_memory.json` keeps up to 100 entries (project path, time, top hypothesis and an error fingerprint) for "seen before" hints. Delete it to clear the history. Reports are written only where you ask (`-o`).
- **Isolation:** OpsPilot never loads the analysed project's `.env` into its own process, so a repository you are debugging cannot change where OpsPilot sends data.

Redaction is a safety net, not a guarantee, which is why cloud use is always opt-in.

## Configuration

Settings come from command-line flags, environment variables, or `~/.config/opspilot/config.env` (dotenv syntax; see [config.env.example](config.env.example), or set `OPSPILOT_CONFIG_FILE`).

| Variable | Default | Meaning |
|---|---|---|
| `OPSPILOT_PROVIDER` | `auto` | `auto` (local Ollama only), `ollama`, `gemini`, `openrouter`, `anthropic` |
| `OPSPILOT_MODEL` | | Model override for the provider tried first |
| `OPSPILOT_ALLOW_CLOUD` | `false` | In `auto` mode, fall back to cloud providers with API keys |
| `OPSPILOT_OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OPSPILOT_OLLAMA_MODEL` | `llama3` | Must already be pulled |
| `GOOGLE_API_KEY` / `OPSPILOT_GEMINI_MODEL` | / `gemini-2.5-flash` | Gemini |
| `ANTHROPIC_API_KEY` / `OPSPILOT_ANTHROPIC_MODEL` | / `claude-haiku-5-5` | Anthropic |
| `OPENROUTER_API_KEY` / `OPSPILOT_OPENROUTER_MODEL` | / required | OpenRouter (any ID from <https://openrouter.ai/models>) |
| `OPSPILOT_REQUEST_TIMEOUT` | `120` | Seconds per LLM request |
| `OPSPILOT_DEADLINE` | `300` | Total seconds for all LLM requests in one run |
| `OPSPILOT_MAX_RETRIES` | `2` | Retries for timeouts, rate limits and 5xx errors only |
| `OPSPILOT_BUILD_TIMEOUT` | `300` | Time limit for `--build-cmd` |
| `OPSPILOT_REDACT` | `true` | Mask likely secrets before sending text to a model |

Cloud model IDs change over time. If a provider reports an unknown model, set the matching `OPSPILOT_*_MODEL` variable.

## Troubleshooting

Start with `opspilot doctor`: it shows the configuration and why each provider is or isn't ready.

- **"No permitted LLM provider is ready"**: start Ollama (the desktop app, or `ollama serve`) and pull the model it names. OpsPilot is local-only by default; use `--provider ...` or `--allow-cloud` for a cloud model. `--no-llm` always works.
- **"No error output was found"**: give OpsPilot the failure directly (`--stdin`, `--error`, `--build-cmd`, `--log-source`). Discovery only reads `*.log` files.
- **"Time budget ... exhausted"**: the model is slow on your hardware. Raise `OPSPILOT_DEADLINE`, or use a smaller model. The first request after starting Ollama includes model load time.
- **"Model returned invalid structured output"**: retry, or use a larger model.
- **The diagnosis looks wrong**: check which facts it cites, run with `--verbose`, pass the actual failing output, or try a larger model.
- **`--debug`** writes provider, timing and retry details to stderr (never prompt contents).

## Limitations

- Diagnosis quality depends on the model; local models make mistakes, and suggested patches rarely apply as-is.
- Log parsing is heuristic and tuned for common formats (Python, Node/TypeScript, JVM, Go, Rust, mypy, nginx-style access logs).
- Remote log sources (S3, Kubernetes, CloudWatch) are lightly tested against real services.

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Security issues: [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
