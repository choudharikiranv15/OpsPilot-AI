# Privacy and data handling

This page describes exactly what OpsPilot reads, what it sends to a language model, and what it stores. It applies to OpsPilot 0.2.0 and later.

## What OpsPilot reads

From the directory you run it in:

| Input | What is read | What is kept |
|---|---|---|
| Log files | `*.log` (and rotations such as `app.log.1`) in `./logs`, `./log`, `./var/log` and the project root. Only the most recent part of each file (bounded tail read). | Error-like lines, de-duplicated |
| `--log-source` | The file, URL or CLI output you name, capped at the last 5 MB | Error-like lines |
| `--error`, `--stdin`, `--build-cmd` | The text you provide, or the command's combined output (capped at 5 MB) | Build/runtime errors and stack frames |
| `.env`, `.env.local`, `.env.development`, `.env.production` | Parsed to learn variable **names** | **Names only.** Values are discarded immediately and never reach output, reports, prompts or history. |
| Source files (`.py`, `.js`, `.ts`, `.go`, `.rb`, `.php`, ...) up to 4 directories deep, max 2,000 files | Scanned for environment variable references such as `os.getenv("X")` | Variable names and the first file that references them |
| Dependency manifests (`requirements.txt`, `package.json`, `go.mod`, ...) | Dependency names and versions | Up to 40 entries, as project context |
| `Dockerfile` / compose files | Existence only | File names |
| Git history (only with `--deployment-analysis`) | Commit hash, author name, date, subject and changed file names | Up to 5 commits |
| Files referenced by stack frames (only when proposing patches) | Up to 3 files, about 60 lines around the referenced line | Sent to the model as context for the patch |

OpsPilot never writes to your project.

## What is sent to the model

One diagnosis request containing the numbered facts and a small project summary (top-level file names, dependency list, Docker file names, `.env` variable names). If a patch is proposed, a second request contains the top hypothesis, the facts it cites, and the file excerpts described above. If the model's reply is malformed, OpsPilot retries once with the same content.

**Before anything is sent, a redaction pass masks** private keys, common API token formats (AWS, GitHub, Slack, OpenAI/Anthropic/OpenRouter, Google, Hugging Face, Stripe), JWTs, bearer tokens, passwords embedded in URLs, values of `key=value` pairs whose key looks secret (`password`, `token`, `api_key`, `secret`, ...), and email addresses. The number of redactions is shown in the output. Redaction is a safety net, not a guarantee: unusual secret formats can slip through. Disable it with `--no-redact` or `OPSPILOT_REDACT=false`.

## Where it is sent

| Setting | Where data can go |
|---|---|
| Default (`provider = auto`) | Only Ollama at `OPSPILOT_OLLAMA_HOST` (default `http://localhost:11434`). If Ollama is unavailable, OpsPilot stops; it does **not** fall back to the cloud. |
| `--allow-cloud` / `OPSPILOT_ALLOW_CLOUD=true` | Ollama first; if it fails, cloud providers for which an API key is configured, in the order Gemini, OpenRouter, Anthropic. |
| `--provider gemini` (or `openrouter`, `anthropic`) | Only that provider. Naming it is your opt-in. |
| `--no-llm` | Nowhere. |

Before the first request, OpsPilot prints the provider, model, and whether it is local or cloud, for example `Using LLM: gemini (gemini-2.5-flash, cloud)`. Each cloud provider's own data-retention policy applies to what you send it.

## What is stored

`~/.opspilot_memory.json` keeps up to 100 entries with the project path, timestamp, top hypothesis, and an error fingerprint (a hash of exception types and status codes), used for "Seen before" hints. Raw logs and evidence are not stored. On POSIX systems the file is created with mode `0600`. Delete the file to clear the history.

Reports are written only where you ask (`-o`). They contain the facts and diagnosis, which may include text copied from your logs.

## Configuration isolation

OpsPilot reads its own settings from environment variables and `~/.config/opspilot/config.env`. It deliberately does **not** load the analysed project's `.env` into its own process, so a repository you are debugging cannot redirect OpsPilot's network traffic (for example through `HTTPS_PROXY`) or change its provider settings.
