# Examples

These are real outputs captured with OpsPilot 0.2.0.dev0 and the default local model `llama3.2` (3B) through Ollama, on a laptop. Paths are shortened. Larger models generally give better hypotheses and patches.

## 1. A missing Python dependency

```bash
opspilot analyze --error 'Traceback (most recent call last):
  File "app/main.py", line 2, in <module>
    import redis
ModuleNotFoundError: No module named '\''redis'\'''
```

```text
Using LLM: ollama (llama3.2, local)
Observed facts (extracted directly, no AI)
  F1 [build_error] --error text: ModuleNotFoundError: No module named 'redis'
  F2 [stack_frame] --error text: Stack frame at app/main.py:2

Diagnosis (AI-generated)
Failed to import required module
  1. Missing dependency in requirements.txt  (dependency, model confidence 0.80)
     cites F1

Missing information
  - Project dependencies beyond 'requirements.txt'

Suggested next checks (review before running)
  - Inspect 'requirements.txt' to verify all dependencies are listed

Dry-run patch suggestions (not applied)
  requirements.txt
  Adding redis as a dependency to resolve the ModuleNotFoundError
  patch does NOT apply to the current file; treat as a sketch
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
flask==3.0.0
redis==4.2.0

LLM: ollama (llama3.2, local) · 2 request(s) · 0 value(s) redacted · 15.1s
```

The diagnosis is right and cites the real error. The model's patch has the right idea but is not a valid unified diff (its lines lack `+` and space prefixes), so OpsPilot marks it "does NOT apply" instead of presenting it as ready to use.

## 2. A service log with several errors

The sample project in [`tests/fixtures/sample_project`](tests/fixtures/sample_project) has a log with Redis timeouts, an HTTP 503 and a Postgres connection error. Its code reads `DATABASE_URL`, which its `.env` does not define.

```bash
cd tests/fixtures/sample_project
opspilot analyze
```

```text
Observed facts (extracted directly, no AI)
  F1 [log_error] logs/app.log: ERROR redis.exceptions.TimeoutError: Timeout reading from socket
  F2 [log_error] logs/app.log: ERROR GET /api/orders failed with status 503
  F3 [log_error] logs/app.log: ERROR Traceback (most recent call last):
  F4 [log_error] logs/app.log: redis.exceptions.TimeoutError: Timeout reading from socket
  F5 [log_error] logs/app.log: ERROR psycopg2.OperationalError: connection refused to db:5432
  F6 [log_summary] logs: Log summary: HTTP status codes 503×1; 4 timeout mentions;
     database/cache errors: redis.exceptions.TimeoutError, psycopg2.OperationalError; ...
  F7 [stack_frame] logs: Stack frame at app/main.py:42
  F8 [config] source code scan: Environment variables referenced in code but not defined
     in the project's .env files (they may still be set at runtime): DATABASE_URL (app/main.py)

Diagnosis (AI-generated)
Application is experiencing intermittent connection issues with Redis and PostgreSQL
  1. Resource exhaustion due to unhandled exceptions in the application
     (resource_exhaustion, model confidence 0.80)
     cites F1, F4

LLM: ollama (llama3.2, local) · 3 request(s) · 0 value(s) redacted · 36.2s
```

The facts are the useful part here: they point straight at Redis timeouts and an unreachable Postgres. The small model's top hypothesis is vague; a larger model, or `--verbose` and a look at the cited facts, gets you further.

## 3. Facts only (nothing leaves your machine)

```bash
opspilot analyze --no-llm
```

This prints the same "Observed facts" section without contacting any model. It is useful on sensitive systems, or as a quick triage step.

## 4. Scripting and CI

```bash
opspilot analyze --stdin --json < build.log > opspilot.json
```

stdout contains a single JSON document (`schema_version: "1"`) with `facts`, `diagnosis.hypotheses[*].evidence`, `suggestions[*].check`, `llm` and `warnings`. Progress messages go to stderr. A minimal CI step:

```bash
npm run build > build.log 2>&1 || opspilot analyze --stdin --no-llm -o opspilot-facts.md < build.log
```

## 5. Using a hosted model

```bash
export ANTHROPIC_API_KEY=...
opspilot analyze --provider anthropic --stdin < build.log
# Using LLM: anthropic (claude-haiku-5-5, cloud)
```

Likely secrets are redacted before sending, and the footer reports how many values were masked. See [docs/privacy.md](docs/privacy.md).
