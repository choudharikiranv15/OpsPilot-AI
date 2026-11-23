# Tests

```bash
pip install -e ".[dev]"
pytest                        # all tests; no network or Ollama required
pytest --cov=opspilot         # with coverage (CI enforces the gate in pyproject.toml)
pytest tests/test_cli_e2e.py  # end-to-end CLI tests only
```

| File | Covers |
|---|---|
| `test_cli_e2e.py` | The real CLI with a fake LLM: JSON contract, citation validation, patch grounding and `git apply --check`, prompt secret canary, local-only provider policy, markup safety, `--stdin`, `--build-cmd`, `--log-source`, reports, `doctor`, `--help` |
| `test_llm.py` | Provider requests and parsing, provider policy, retries and deadline, structured output repair. Defines `FakeSession`/`FakeResponse`. |
| `test_evidence.py` | Fact extraction: de-duplication, stack frames, build errors, config and git facts, prompt delimiting, fixer targets |
| `test_secret_exposure.py` | `.env` and Docker values never reach context, output or reports |
| `test_redact.py` | Secret/email redaction and router integration |
| `test_memory.py` | History file: minimal fields, cap, corruption handling, fingerprint matching |
| `test_logs.py`, `test_production_logs.py` | Log discovery, bounded reads, remote source validation and command construction |
| `test_context.py` | Dependency manifests, `.env` parsing, env-reference scan, git history |
| `test_pattern_analysis.py` | Regex error statistics and severity heuristic |

`fixtures/sample_project/` is a small project with logs, source code and a `.env` containing a fake canary secret. It is used by the end-to-end tests and the CI smoke test.
