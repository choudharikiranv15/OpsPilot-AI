# Configuration

OpsPilot reads settings from, in order of precedence:

1. Command-line flags (`--provider`, `--model`, `--allow-cloud`, `--no-redact`)
2. Environment variables
3. The user config file, `~/.config/opspilot/config.env` (dotenv syntax). Set `OPSPILOT_CONFIG_FILE` to use another path.

The `.env` file of the project being analysed is **never** used for OpsPilot's own settings. Run `opspilot doctor` to see the effective configuration and which providers are ready.

A commented template is in [`config.env.example`](../config.env.example).

## Provider selection

| Variable | Default | Meaning |
|---|---|---|
| `OPSPILOT_PROVIDER` | `auto` | `auto`, `ollama`, `gemini`, `openrouter` or `anthropic`. `auto` uses only local Ollama unless `OPSPILOT_ALLOW_CLOUD` is true. Naming a cloud provider opts in to it. |
| `OPSPILOT_MODEL` | unset | Overrides the model of the provider that will be tried first. |
| `OPSPILOT_ALLOW_CLOUD` | `false` | In `auto` mode, fall back to cloud providers that have an API key when Ollama fails. |

## Providers

| Variable | Default | Notes |
|---|---|---|
| `OPSPILOT_OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OPSPILOT_OLLAMA_MODEL` | `llama3.2` | Must already be pulled (`ollama pull <model>`) |
| `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) | unset | Enables Gemini |
| `OPSPILOT_GEMINI_MODEL` | `gemini-2.5-flash` | |
| `ANTHROPIC_API_KEY` | unset | Enables Anthropic |
| `OPSPILOT_ANTHROPIC_MODEL` | `claude-haiku-5-5` | |
| `OPENROUTER_API_KEY` | unset | Enables OpenRouter |
| `OPSPILOT_OPENROUTER_MODEL` | unset (required) | Any model ID from <https://openrouter.ai/models>. There is no default because free model IDs change often. |

Each API key can also be given with an `OPSPILOT_` prefix (for example `OPSPILOT_GOOGLE_API_KEY`). Keys are never printed.

Cloud model IDs change over time. If a provider reports an unknown model, set the corresponding `OPSPILOT_*_MODEL` variable to a current model ID.

## Limits

| Variable | Default | Meaning |
|---|---|---|
| `OPSPILOT_REQUEST_TIMEOUT` | `120` | Seconds allowed for a single LLM request |
| `OPSPILOT_DEADLINE` | `300` | Total seconds for all LLM requests in one command |
| `OPSPILOT_MAX_RETRIES` | `2` | Retries for transient errors (timeouts, rate limits, 5xx, connection errors). Other errors are not retried. |
| `OPSPILOT_BUILD_TIMEOUT` | `300` | Seconds `--build-cmd` may run. On timeout the output captured so far is analysed. |

## Privacy

| Variable | Default | Meaning |
|---|---|---|
| `OPSPILOT_REDACT` | `true` | Mask likely secrets and emails before sending text to a model (same as omitting `--no-redact`) |

## Fixed limits (not configurable)

- Log sources and command output: last 5 MB
- Local log discovery: 5 most recent `*.log` files, last 256 KB of each, about 10,000 characters in total
- Facts: up to 25 log errors, 15 build errors and 10 stack frames
- History file: 100 entries
