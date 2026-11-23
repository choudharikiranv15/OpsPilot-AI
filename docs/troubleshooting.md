# Troubleshooting

Start with:

```bash
opspilot doctor
```

It shows the config file in use, which providers are permitted, and why each one is or isn't ready.

## "No permitted LLM provider is ready"

**Ollama is not reachable.** Install it from <https://ollama.com/download> and make sure it is running (the desktop app, or `ollama serve`). If it runs elsewhere, set `OPSPILOT_OLLAMA_HOST`.

**Model is not installed.** OpsPilot does not download models. Run the command it prints, for example `ollama pull llama3.2`, or pick a model you already have: `opspilot analyze --model qwen2.5:7b` (see `ollama list`).

**You expected a cloud provider to be used.** By default OpsPilot is local-only and does not fall back to the cloud. Use `--provider gemini` (or `anthropic` / `openrouter`), or `--allow-cloud`. See [privacy.md](privacy.md).

You can always run `opspilot analyze --no-llm` to see the extracted facts without any model.

## "No error output was found"

OpsPilot found no error lines to analyse. Give it the failure directly:

```bash
npm run build 2>&1 | opspilot analyze --stdin
opspilot analyze --error "paste the error here"
opspilot analyze --log-source path/to/service.log
```

Automatic log discovery only looks at `*.log` files in `./logs`, `./log`, `./var/log` and the project root.

## `--stdin` says it expects piped input

`--stdin` reads from a pipe. Use `command 2>&1 | opspilot analyze --stdin` (the `2>&1` includes stderr, where most errors go).

## `--build-cmd` problems

- **"Command not found"**: the command is not on `PATH`. Commands run without a shell, so shell features (`&&`, pipes, `$VAR`) do not work. Wrap them in a script, or pipe into `--stdin` instead.
- **Timed out**: long-running commands such as dev servers (`ng serve`, `npm start`) never finish. OpsPilot analyses what was printed before the timeout (`OPSPILOT_BUILD_TIMEOUT`, default 300 s). Prefer one-shot commands such as `npm run build` or `pytest`.

## "LLM error: Model returned invalid structured output"

The model did not return valid JSON even after one retry. Smaller models do this more often. Try again, or use a larger model with `--model`.

## "Time budget of ...s exhausted"

The model is too slow for the configured deadline. Raise `OPSPILOT_DEADLINE` and `OPSPILOT_REQUEST_TIMEOUT`, or use a smaller or faster model. The first request after starting Ollama also includes model load time.

## The diagnosis looks wrong

Check which facts the hypothesis cites. "Cites no extracted fact" means it is a guess. Useful steps:

- `--verbose` shows every extracted fact.
- Give OpsPilot the actual failing output (`--stdin` / `--error`) rather than relying on discovered logs.
- Use a larger model.
- Use `--deployment-analysis` if a recent change may be responsible.

## Patch says "does NOT apply"

The model wrote a patch that does not match the current file. Treat it as a sketch of the idea, not as a change you can apply.

## Debug output

`--debug` writes detailed logs to stderr: provider, timing, retries and prompt sizes. Prompt contents are not logged.

## Clearing history

Delete `~/.opspilot_memory.json`. If the file is ever unreadable, OpsPilot moves it aside (`.opspilot_memory.json.corrupt-<timestamp>`) and continues.
