# Contributing

Thanks for helping improve OpsPilot. The priority is a small, reliable tool: secure, honest about uncertainty, and easy to install. Please discuss large features in an issue first.

## Setup

```bash
git clone https://github.com/choudharikiranv15/OpsPilot-AI.git
cd OpsPilot-AI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install          # optional: ruff, gitleaks and bandit on commit
```

## Before opening a pull request

```bash
ruff check . && ruff format --check .
pytest --cov=opspilot       # must stay at or above the coverage gate in pyproject.toml
```

Every change needs tests. The suite must not need network access or a running Ollama: use the fake HTTP session in `tests/test_llm.py` and the CLI helpers in `tests/test_cli_e2e.py`.

## Ground rules

- **No execution or writes from model output.** Suggestions stay dry-run.
- **No silent data egress.** Anything that sends data to a new destination must be opt-in and documented in `docs/privacy.md`.
- **Never collect secret values.** Use names only, and add a canary test for new inputs.
- **Untrusted text is data.** Print it with Rich `Text`/`escape()`; put it inside delimiters in prompts.
- **Bounded work.** New inputs need size, count and time limits.
- **Docs match behaviour.** Update `README.md`, `docs/` and `CHANGELOG.md` (`[Unreleased]`) in the same pull request.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) prefixes: `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`, `refactor:`.
