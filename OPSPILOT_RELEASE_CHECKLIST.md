# OpsPilot AI CLI: Release Checklist (path to 0.2.0)

Companion to [`OPSPILOT_AUDIT_REPORT.md`](OPSPILOT_AUDIT_REPORT.md). Finding IDs (BUG-xx, SEC-xx, AI-xx) refer to that report.

**How to use this file**
- Tick the checkbox when the acceptance criteria are met, and update `Status`.
- **Priority:** `P0` = release blocker · `P1` = required for 0.2.0 · `P2` = should have for 0.2.0 · `P3` = post-release.
- **Status values:** `Not started` · `In progress` · `Blocked` · `Done` · `Won't do` (add a reason).
- **Release gate:** 0.2.0 ships only when every `P0` and `P1` item is `Done` or `Won't do` with a justification.

**Progress summary** (update manually)

| Phase | Items | Done |
|---|---:|---:|
| 1. Immediate critical issues | 8 | 0 |
| 2. Security and reliability fixes | 14 | 0 |
| 3. Core product completion | 13 | 0 |
| 4. Testing and validation | 11 | 0 |
| 5. Packaging and documentation | 11 | 0 |
| 6. Release and post-release | 10 | 0 |
| **Total** | **67** | **0** |

---

## Decisions needed before starting

These change the scope of several items below. Record each decision here.

- [ ] **D-01: Primary user for v1.** Recommendation: the developer debugging a local or CI failure. _Decision:_
- [ ] **D-02: Cloud providers in 0.2.0?** Recommendation: allowed only by explicit opt-in. _Decision:_
- [ ] **D-03: `troubleshoot` command.** Recommendation: merge its checks into `analyze`, remove the command. _Decision:_
- [ ] **D-04: Remote log sources (S3/k8s/CloudWatch).** Recommendation: defer, or ship behind `--experimental`. _Decision:_
- [ ] **D-05: HTTP client.** Recommendation: `httpx` only. _Decision:_
- [ ] **D-06: Config system.** Recommendation: `pydantic-settings` as the single source, with no `constants.py` duplicates. _Decision:_

---

## Phase 1: Immediate Critical Issues

- [ ] **P1-01: Feature freeze on `main`**
  - Category: Process · Priority: P0 · Status: Not started · Depends on: none
  - Acceptance: no new features merge until Phase 1 and Phase 2 P0/P1 items are done. Freeze noted in README/CONTRIBUTING or the repo description.
  - Evidence: ~3,600 untested lines landed 2026-08-10 within ~30 minutes (audit §2.2)

- [ ] **P1-02: Restore a working clean install**
  - Category: Packaging · Priority: P0 · Status: Not started · Depends on: D-05
  - Acceptance: in a fresh venv with no extras, `pip install .` and then `opspilot --version` and `opspilot --help` succeed. Every runtime import is declared in `[project].dependencies`; declared-but-unused deps are removed.
  - Evidence: BUG-01; `pyproject.toml:45-53`; `opspilot/utils/llm_providers.py:20`; `opspilot/context/production_logs.py:3`

- [ ] **P1-03: Add a clean-wheel install smoke job to CI**
  - Category: CI · Priority: P0 · Status: Not started · Depends on: P1-02
  - Acceptance: CI builds the wheel, installs it into a new venv **without** dev or all extras on ubuntu, windows, and macos, and runs `--version`, `--help`, and `analyze --mode explain` on a fixture. Re-introducing an undeclared import makes this job fail.
  - Evidence: BUG-18 (twine/kubernetes pull `requests` transitively and mask the break)

- [ ] **P1-04: Bump and single-source the version**
  - Category: Release · Priority: P0 · Status: Not started · Depends on: none
  - Acceptance: version is `0.2.0.dev0` (or similar) in exactly one place; `opspilot --version` reads it via `importlib.metadata`; `constants.VERSION` removed.
  - Evidence: BUG-16; `pyproject.toml:7`; `opspilot/constants.py:4`; PyPI already hosts a different 0.1.6

- [ ] **P1-05: Fix or disable the `troubleshoot` crash**
  - Category: Bug · Priority: P0 · Status: Not started · Depends on: D-03
  - Acceptance: `opspilot troubleshoot` either runs to completion on the fixture project or is removed or hidden from `--help`. No `TypeError`.
  - Evidence: BUG-02; `opspilot/workflow.py:341` vs `opspilot/tools/env_tools.py:4`

- [ ] **P1-06: Stop emitting `.env` values anywhere**
  - Category: Security · Priority: P0 · Status: Not started · Depends on: none
  - Acceptance: context stores env **names** (and a set/unset flag) only. A canary value in fixture `.env`, Dockerfile, and docker-compose files never appears in stdout, stderr, `-o` reports (json/md/txt), the memory file, or LLM prompts.
  - Evidence: SEC-01; `opspilot/context/env.py:8-45`; `opspilot/cli.py:496-503, 566-577`

- [ ] **P1-07: Make CI green**
  - Category: CI · Priority: P0 · Status: Not started · Depends on: P1-02
  - Acceptance: `ruff check` and `ruff format --check` pass. Python 3.10 is removed from the matrix (or support is restored). The duplicate `tests.yml` and `ci.yml` test jobs are merged. All jobs are green on `main`.
  - Evidence: BUG-17; `.github/workflows/tests.yml:14`; `gh run list` failures since 2026-08-10

- [ ] **P1-08: Add a temporary notice to the README until 0.2.0**
  - Category: Docs · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: the README states the current status honestly (alpha; known limitations; `main` vs PyPI 0.1.6).
  - Evidence: Appendix B of the audit

---

## Phase 2: Security and Reliability Fixes

- [ ] **P2-01: Make the tool local-first; no silent cloud fallback**
  - Category: Security/Privacy · Priority: P0 · Status: Not started · Depends on: D-02
  - Acceptance: the default provider is Ollama. Cloud providers are used only when configured **and** opted in (e.g. `--provider gemini` or `OPSPILOT_ALLOW_CLOUD=1`). Fallback never crosses from local to cloud. Provider and model are printed (to stderr) before any request. A test asserts that no cloud call happens when Ollama fails and no opt-in is set.
  - Evidence: SEC-02; `opspilot/utils/llm_providers.py:552-640`

- [ ] **P2-02: Explicit, predictable configuration loading**
  - Category: Security · Priority: P0 · Status: Not started · Depends on: D-06
  - Acceptance: OpsPilot never loads the *analyzed project's* `.env` into its own environment. User config comes from the env vars and/or `~/.config/opspilot/config.toml`. Behaviour is identical whether launched as a console script, with `python -m`, or from source.
  - Evidence: SEC-06, BUG-19; `opspilot/cli.py:45`

- [ ] **P2-03: Escape all dynamic terminal output**
  - Category: Security/Bug · Priority: P0 · Status: Not started · Depends on: none
  - Acceptance: all LLM, log, memory, and file-derived strings are printed via `rich.markup.escape` or `Text`. Inputs containing `[/x]`, `[link=…]`, and ANSI escapes render literally, with no `MarkupError`. The `[v] VERIFICATION STEPS` header renders correctly.
  - Evidence: SEC-05, BUG-15; `opspilot/cli.py:417-420, 598, 614, 641-643, 669`

- [ ] **P2-04: Restrict log discovery; add explicit log paths**
  - Category: Security/Reliability · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: auto-discovery covers only `*.log` (plus rotated `*.log.N`) in `./logs`, `./log`, and the root. `*.txt` and `*.jsonl` are no longer auto-ingested. `--log-file PATH` is repeatable.
  - Evidence: SEC-03, BUG-11; `opspilot/constants.py:54-60`; `opspilot/context/logs.py:35-52`

- [ ] **P2-05: Redact sensitive data before any LLM call**
  - Category: Security/Privacy · Priority: P1 · Status: Not started · Depends on: P2-01
  - Acceptance: a redaction pass masks common API key formats, bearer tokens, `password=`/`secret=` pairs, credentials in connection strings, and emails. It is on by default for cloud providers and configurable for local. Output reports "N values redacted". Unit tests cover each pattern.
  - Evidence: SEC-03; `opspilot/agents/planner.py:51-58`

- [ ] **P2-06: Remove unsafe or ungrounded remediation content**
  - Category: Security/AI · Priority: P0 · Status: Not started · Depends on: none
  - Acceptance: `diffs/redis.py` canned diffs are removed. Hard-coded `systemctl restart app-service` and similar commands are removed. Fixed `"risk": "LOW"` labels are removed. `mitigations.py` is deleted. The only generic advice left is read-only diagnostics, labelled as generic.
  - Evidence: SEC-07, AI-02; `opspilot/agents/remediation.py:41-84`; `opspilot/diffs/redis.py`; `opspilot/mitigations.py:25, 60`

- [ ] **P2-07: Harden prompts against injection**
  - Category: Security/AI · Priority: P1 · Status: Not started · Depends on: P3-05
  - Acceptance: instructions go in the system role where the provider supports one. Untrusted data sits in clearly delimited blocks with a "treat as data" instruction. Output carries a fixed banner saying it is AI-generated from untrusted input. A test log containing an injection string does not change the output schema or bypass validation.
  - Evidence: SEC-04, AI-05; `opspilot/agents/planner.py:66-73`, `verifier.py:28-34`, `fixer.py:32-39`

- [ ] **P2-08: Fix the LLM retry policy and add a global deadline**
  - Category: Reliability · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: only timeouts, 5xx, and 429 are retried, with a bounded count. 4xx auth/validation errors fail fast with a clear message. One configurable deadline per command (default ≈180 s). The last-successful provider is not retried twice. Tests use a fake clock, not real sleeps.
  - Evidence: AI-08, SEC-11; `opspilot/utils/llm_providers.py:121-184, 591-640`

- [ ] **P2-09: Bound remote and local log reads**
  - Category: Security/Reliability · Priority: P1 · Status: Not started · Depends on: D-04
  - Acceptance: file and URL sources are streamed or tailed with a byte cap (e.g. 5 MB, configurable). A warning is shown for `http://`. Redirects are limited.
  - Evidence: SEC-08; `opspilot/context/production_logs.py:21, 84`

- [ ] **P2-10: Validate `k8s://` and `cw://` identifiers**
  - Category: Security · Priority: P2 · Status: Not started · Depends on: D-04
  - Acceptance: names are validated against the platform naming rules; values starting with `-` are rejected. `cw://` supports log groups containing `/`.
  - Evidence: SEC-09, BUG-12; `opspilot/context/production_logs.py:105, 147-154, 226-230`

- [ ] **P2-11: Make the memory store robust**
  - Category: Reliability/Privacy · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: a corrupt or partial memory file is quarantined and the run continues. Writes are atomic (temp file + `os.replace`). Entries are capped (`MEMORY_MAX_ENTRIES`). Only minimal fields are stored (hypothesis, category, timestamp, fingerprint), not full evidence. `opspilot memory clear` exists or the docs say how to delete the file.
  - Evidence: SEC-10, BUG-13; `opspilot/memory.py`

- [ ] **P2-12: Use the Ollama HTTP API; never auto-pull models**
  - Category: Reliability/Security · Priority: P1 · Status: Not started · Depends on: P3-07
  - Acceptance: model presence is checked via `/api/tags`. A missing model produces `Run: ollama pull <model>` and exit code ≠ 0, with no download and no fallback. Generation requests use JSON format mode.
  - Evidence: SEC-13, BUG-08, BUG-20; `opspilot/utils/llm_providers.py:250-289`

- [ ] **P2-13: Harden CI/CD supply chain**
  - Category: Security/CI · Priority: P1 · Status: Not started · Depends on: P1-07
  - Acceptance: PyPI Trusted Publishing (OIDC) through a protected `pypi` environment; the `PYPI_API_TOKEN` secret is deleted. Actions are pinned by commit SHA, with Dependabot enabled for actions and pip. `pip-audit` and `bandit -ll` block the build (no `|| true`).
  - Evidence: SEC-12; `.github/workflows/ci.yml:97, 101, 150-152`

- [ ] **P2-14: Document the `--build-cmd` trust model**
  - Category: Security/Docs · Priority: P2 · Status: Not started · Depends on: none
  - Acceptance: the docs state that the command runs with the user's privileges in the project directory. The command is never read from project config without confirmation.
  - Evidence: SEC-14; `opspilot/cli.py:460-484`

---

## Phase 3: Core Product Completion

- [ ] **P3-01: Make `--json` output strictly valid**
  - Category: Bug/UX · Priority: P0 · Status: Not started · Depends on: none
  - Acceptance: in `--json` mode, stdout contains only one JSON document matching a documented schema (`docs/output-schema.json`). All status, progress, and warnings go to stderr. All `print()` calls in library modules are replaced by logging. A test parses stdout.
  - Evidence: BUG-05; `opspilot/cli.py:48, 576-577, 693-694`; `print()` in `production_logs.py`, `deployment_history.py`, `verifier.py`

- [ ] **P3-02: Fix report and summary correctness**
  - Category: Bug · Priority: P0 · Status: Not started · Depends on: P3-01
  - Acceptance: reports include the suggestions actually shown. The final confidence and verdict come from the verification step. Summary, JSON, and file report agree.
  - Evidence: BUG-06; `opspilot/cli.py:591-592, 628-655, 669-680`

- [ ] **P3-03: Clean up modes and flags**
  - Category: Product · Priority: P1 · Status: Not started · Depends on: D-03
  - Acceptance: `--mode deep` is removed or implemented with distinct, documented behaviour. `--verbose` on `analyze` either does something documented or is removed. `explain` / `--no-llm` performs zero LLM calls (test asserts it).
  - Evidence: BUG-07; `opspilot/cli.py:309-322, 381-412`

- [ ] **P3-04: Merge `troubleshoot` checks into `analyze` (or fix it fully)**
  - Category: Product · Priority: P1 · Status: Not started · Depends on: D-03, P1-05
  - Acceptance (merge path): deterministic checks become "Observed facts" in `analyze`: missing env vars detected from code usage (`get_required_env_vars`), recent git changes, resource/timeout/connection flags, stack-trace file locations. The hard-coded confidence constants are gone and the `troubleshoot` command is removed.
  - Acceptance (keep path): BUG-03 and BUG-04 are fixed and every phase is reachable and tested.
  - Evidence: BUG-02/03/04; `opspilot/workflow.py`

- [ ] **P3-05: Use structured, validated LLM outputs**
  - Category: AI · Priority: P0 · Status: Not started · Depends on: none
  - Acceptance: pydantic models for the planner, verifier, and fixer outputs. Confidence is clamped to [0,1], and wrong types are rejected. On invalid output: at most one repair attempt, then a clear "model returned invalid output" message (no silent `Hypothesis: None`).
  - Evidence: AI-01, BUG-22; `opspilot/agents/planner.py:75-93`; `opspilot/agents/verifier.py:49-52`

- [ ] **P3-06: Ground the output with numbered evidence and citations**
  - Category: AI · Priority: P1 · Status: Not started · Depends on: P3-05
  - Acceptance: deterministic evidence items get IDs. Every stage receives the same evidence bundle. Each hypothesis lists `supporting_evidence` IDs; hypotheses citing no valid IDs are dropped or flagged. The output separates **Observed facts** from **Hypotheses**. Numeric confidence is replaced in the UI by an evidence-based label.
  - Evidence: AI-01, AI-04, AI-11

- [ ] **P3-07: Make provider and model configurable; add `opspilot doctor`**
  - Category: Product/UX · Priority: P1 · Status: Not started · Depends on: D-06, P2-02
  - Acceptance: model and provider are settable via env/config/flag, with one source of defaults. `opspilot doctor` reports the configured provider, reachability, model presence, cloud opt-in state, and config file location.
  - Evidence: BUG-08, AI-07; `opspilot/constants.py:84-90`; `opspilot/settings.py:40-53`

- [ ] **P3-08: Validate fixer suggestions**
  - Category: AI · Priority: P1 · Status: Not started · Depends on: P3-05
  - Acceptance: suggestions whose `file` doesn't exist in the project are dropped. Each diff is dry-run checked (`git apply --check` or equivalent) and labelled "applies cleanly" or "does not apply". Nothing is ever written to disk.
  - Evidence: AI-03; `opspilot/agents/fixer.py`

- [ ] **P3-09: Improve prompt context budgeting**
  - Category: AI · Priority: P2 · Status: Not started · Depends on: P3-06
  - Acceptance: one shared size budget across prompts. Error lines plus surrounding context are prioritised, newest first, instead of head-truncating logs. Prompt size is shown with `--debug`.
  - Evidence: AI-06; `opspilot/agents/planner.py:53`

- [ ] **P3-10: Fix `--build-cmd` on Windows and for long-running commands**
  - Category: Bug · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: the executable is resolved via `shutil.which` (so `npm`, `ng` and other `.cmd` shims work). Windows paths are not mangled (no POSIX `shlex` on Windows). On timeout, partial output is kept and analyzed. Docs stop recommending `ng serve`.
  - Evidence: BUG-09; `opspilot/cli.py:460-484`

- [ ] **P3-11: Fix `--stdin` for slow producers**
  - Category: Bug · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: when `--stdin` is given and stdin is not a TTY, read to EOF on all platforms. Tested with a producer that sleeps before writing.
  - Evidence: BUG-10; `opspilot/cli.py:435-453`

- [ ] **P3-12: Remove dead and duplicate code**
  - Category: Maintainability · Priority: P1 · Status: Not started · Depends on: D-05, D-06
  - Acceptance: `utils/llm_providers_async.py`, `graph/`, `memory_redis.py`, `mitigations.py`, and one of `logger.py`/`logging_config.py` are removed, as are `examples/modernization_demo.py`, the tracked `opspilot_ai-0.1.4/` and `opspilot_ai-0.1.5/` copies, and the empty `test-angular-project/`. `runbooks.py` is moved to a branch or kept untouched and documented as unused. Unused extras (`aws`, `k8s`, `redis`) are removed. `__init__.py` is added to `agents/`, `commands/`, and `diffs/` (if kept).
  - Evidence: audit §2.4, §4.3 (A1, A7)

- [ ] **P3-13: Refactor `cli.analyze` into testable stages**
  - Category: Maintainability · Priority: P2 · Status: Not started · Depends on: P3-01, P3-05
  - Acceptance: separate functions or modules for input acquisition, context collection, evidence, diagnosis, and rendering, passing typed data between them. `cli.py` only parses flags and renders.
  - Evidence: audit §4.3 (A2, A5)

---

## Phase 4: Testing and Validation

- [ ] **P4-01: Fake LLM provider and CLI end-to-end harness**
  - Category: Testing · Priority: P0 · Status: Not started · Depends on: P3-05
  - Acceptance: a deterministic fake provider can be injected (env var or fixture). Typer `CliRunner` tests cover every flag and mode on fixture projects. No network or Ollama access in the unit or e2e suite.
  - Evidence: `cli.py` coverage 0%; audit §7

- [ ] **P4-02: Secret-canary regression test**
  - Category: Security testing · Priority: P0 · Status: Not started · Depends on: P1-06, P4-01
  - Acceptance: the canary never appears in stdout, stderr, reports, memory, or captured prompts, across all modes.
  - Evidence: SEC-01, SEC-03

- [ ] **P4-03: Provider-policy test**
  - Category: Security testing · Priority: P0 · Status: Not started · Depends on: P2-01, P4-01
  - Acceptance: with Ollama failing and a cloud key present but no opt-in, zero cloud requests are made (mocked HTTP asserts no calls).
  - Evidence: SEC-02

- [ ] **P4-04: JSON contract test**
  - Category: Testing · Priority: P0 · Status: Not started · Depends on: P3-01
  - Acceptance: stdout parses and validates against the published schema for each mode.
  - Evidence: BUG-05

- [ ] **P4-05: Markup and terminal safety tests**
  - Category: Security testing · Priority: P1 · Status: Not started · Depends on: P2-03
  - Acceptance: bracketed and ANSI input from logs and the fake LLM renders literally; no crash.
  - Evidence: SEC-05

- [ ] **P4-06: Malformed-LLM-output tests**
  - Category: Testing · Priority: P1 · Status: Not started · Depends on: P3-05
  - Acceptance: non-JSON, wrong types (`"high"`, `85`), missing fields, and empty responses each produce a defined, user-visible outcome.
  - Evidence: AI-01, BUG-22

- [ ] **P4-07: Context-collector unit tests**
  - Category: Testing · Priority: P1 · Status: Not started · Depends on: P2-04
  - Acceptance: fixtures for `.env` parsing edge cases, each dependency ecosystem, log discovery and tailing, the build-error parser (tsc, ng, pytest, npm, go, cargo, maven samples), and git deployment correlation (temporary repo with backdated commits, timezone handling).
  - Evidence: coverage 0–10% for `context/env.py`, `logs.py`, `deps.py`, `deployment_history.py`, `tools/__init__.py`

- [ ] **P4-08: Router reliability tests**
  - Category: Testing · Priority: P1 · Status: Not started · Depends on: P2-08
  - Acceptance: 401 not retried; 429/5xx/timeout retried within bounds; global deadline enforced; fake clock (no real sleeps); `pytest-timeout` configured.
  - Evidence: AI-08; one unexplained suite hang during the audit

- [ ] **P4-09: Coverage gate**
  - Category: Testing/CI · Priority: P1 · Status: Not started · Depends on: P4-01…P4-08
  - Acceptance: CI fails below 70% line coverage on `opspilot/` (after dead code is removed). Coverage is reported per module.
  - Evidence: current 21%

- [ ] **P4-10: Golden-set diagnosis evaluation**
  - Category: AI evaluation · Priority: P2 · Status: Not started · Depends on: P3-06
  - Acceptance: 15–25 fixture incidents with expected root-cause categories. A script reports schema-valid rate (target 100%), citation validity (target 100%), and category accuracy with the default local model (record the baseline; target ≥70% before 1.0). Results are recorded in `docs/evaluation.md`.
  - Evidence: AI-10

- [ ] **P4-11: Cross-platform runtime validation**
  - Category: Testing · Priority: P1 · Status: Not started · Depends on: P1-03, P4-01
  - Acceptance: the e2e suite runs on Windows, macOS, and Linux with Python 3.11, 3.12, and 3.13 in CI. One manual smoke run with a real Ollama model on each OS is recorded in release notes.
  - Evidence: audit ran runtime checks on Windows only

---

## Phase 5: Packaging and Documentation

- [ ] **P5-01: Rewrite the README around the real workflow**
  - Category: Docs · Priority: P0 · Status: Not started · Depends on: Phase 3 P0/P1
  - Acceptance: describes only shipped behaviour. Install via `pipx`. Ollama setup including **model choice**. Three core examples (`--stdin`, `--log-file`, `--build-cmd`). Correct Python version. Honest limitations section. Every Appendix B discrepancy in the audit is closed.
  - Evidence: audit Appendix B

- [ ] **P5-02: Write `docs/privacy.md`**
  - Category: Docs/Security · Priority: P0 · Status: Not started · Depends on: P2-01, P2-05
  - Acceptance: states exactly which data goes to which provider, when, how to stay fully local, what is redacted, and where memory is stored.
  - Evidence: SEC-02, SEC-03

- [ ] **P5-03: Write `docs/configuration.md` and `docs/troubleshooting.md`**
  - Category: Docs · Priority: P1 · Status: Not started · Depends on: P3-07
  - Acceptance: every setting is listed with its default. Covers common errors (no provider, model missing, timeout, invalid JSON from model) and `opspilot doctor` usage.
  - Evidence: `.env.example` lists settings that have no effect today

- [ ] **P5-04: Remove or relocate aspirational and inaccurate docs**
  - Category: Docs · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: SaaS/Lambda sections removed from `DEPLOYMENT.md` (or the file is deleted). `PRODUCTION_DEBUGGING_RESEARCH.md` moved to `docs/ideas/` and marked as non-roadmap. `UPGRADE_GUIDE.md` deleted or corrected. `ARCHITECTURE.md` trimmed to the actual architecture. `EXAMPLES.md` uses real captured output.
  - Evidence: audit §2.3, Appendix B

- [ ] **P5-05: Add `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`**
  - Category: Docs/Process · Priority: P1 · Status: Not started · Depends on: none
  - Acceptance: the CHANGELOG follows Keep a Changelog and includes the 0.1.x history summary. `SECURITY.md` gives a private reporting channel. `CONTRIBUTING.md` requires tests with features.
  - Evidence: no changelog or tags exist

- [ ] **P5-06: Convert `PYPI_DEPLOYMENT.txt` to `RELEASING.md`**
  - Category: Docs/Process · Priority: P2 · Status: Not started · Depends on: P2-13
  - Acceptance: documents the tag-driven Trusted Publishing flow and the TestPyPI dry run.
  - Evidence: `PYPI_DEPLOYMENT.txt`

- [ ] **P5-07: Fix package metadata**
  - Category: Packaging · Priority: P1 · Status: Not started · Depends on: P1-02
  - Acceptance: `Development Status :: 3 - Alpha`. Either a `py.typed` file is added or the claim and classifier are removed. Accurate keywords, Python 3.11–3.13 classifiers, and project URLs. Version caps reviewed (`rich<14`, `structlog<25`). `twine check` passes.
  - Evidence: `pyproject.toml:15-29, 96`

- [ ] **P5-08: Add a module entry point**
  - Category: Packaging · Priority: P2 · Status: Not started · Depends on: none
  - Acceptance: `python -m opspilot --help` works (`opspilot/__main__.py`).
  - Evidence: BUG-14

- [ ] **P5-09: Clean the sdist and wheel contents**
  - Category: Packaging · Priority: P2 · Status: Not started · Depends on: P3-12
  - Acceptance: the sdist contains source, tests, README, LICENSE, CHANGELOG and no stale files. `MANIFEST.in` is updated for the doc changes. Wheel contents are listed and reviewed.
  - Evidence: `MANIFEST.in`

- [ ] **P5-10: Run a TestPyPI dry run**
  - Category: Release · Priority: P0 · Status: Not started · Depends on: P2-13, P5-07
  - Acceptance: a tag on a release-candidate branch publishes to TestPyPI. `pipx install --index-url … opspilot-ai==0.2.0rc1` works on all three OSes.
  - Evidence: audit §11

- [ ] **P5-11: Add CLI help text quality pass**
  - Category: UX · Priority: P2 · Status: Not started · Depends on: P3-03
  - Acceptance: every command and flag has an accurate help string and an example. No flags that do nothing.
  - Evidence: BUG-07

---

## Phase 6: Release and Post-Release

- [ ] **P6-01: Go/no-go review against the audit §14 criteria**
  - Category: Release · Priority: P0 · Status: Not started · Depends on: all P0/P1 items
  - Acceptance: every gate box in audit §14 is checked, with links to CI runs and evidence.
  - Evidence: audit §14

- [ ] **P6-02: Tag and publish `v0.2.0` via Trusted Publishing**
  - Category: Release · Priority: P0 · Status: Not started · Depends on: P6-01
  - Acceptance: the `v0.2.0` tag triggers CI build, clean-install smoke tests, and the PyPI publish. The GitHub Release contains notes and artifacts.
  - Evidence: SEC-12

- [ ] **P6-03: Post-release verification**
  - Category: Release · Priority: P0 · Status: Not started · Depends on: P6-02
  - Acceptance: within 24 h, `pipx install opspilot-ai==0.2.0` succeeds on all three OSes and a fixture analysis completes with a local model.
  - Evidence: none yet

- [ ] **P6-04: Set up issue templates and a feedback loop**
  - Category: Process · Priority: P2 · Status: Not started · Depends on: P6-02
  - Acceptance: bug and diagnosis-quality issue templates (asking for `opspilot doctor` output and redacted input).
  - Evidence: none yet

- [ ] **P6-05: Add the misdiagnoses from feedback to the golden set**
  - Category: AI evaluation · Priority: P2 · Status: Not started · Depends on: P4-10, P6-04
  - Acceptance: every reported wrong diagnosis becomes a fixture with an expected category.
  - Evidence: AI-10

- [ ] **P6-06: (Post-release) Runbook matching**
  - Category: Feature · Priority: P3 · Status: Not started · Depends on: P3-06
  - Acceptance: project runbooks matched to evidence and cited as facts, with tests. Uses the existing `context/runbooks.py` as a starting point.
  - Evidence: `opspilot/context/runbooks.py` (unwired)

- [ ] **P6-07: (Post-release) Validated remote log sources**
  - Category: Feature · Priority: P3 · Status: Not started · Depends on: D-04, P2-09, P2-10
  - Acceptance: S3, k8s, and CloudWatch each tested against a real or emulated service (e.g. kind, LocalStack). Documented prerequisites.
  - Evidence: mock-only tests today

- [ ] **P6-08: (Post-release) Additional opt-in providers**
  - Category: Feature · Priority: P3 · Status: Not started · Depends on: P2-01, P3-07
  - Acceptance: Anthropic and/or a generic OpenAI-compatible endpoint, behind the same opt-in and redaction policy, with current model IDs verified against provider docs.
  - Evidence: `AnthropicProvider` exists but is unrouted

- [ ] **P6-09: (Post-release) Better "seen before" matching**
  - Category: Feature · Priority: P3 · Status: Not started · Depends on: P2-11
  - Acceptance: matching by error fingerprint, not by project path. It never short-circuits analysis.
  - Evidence: BUG-03, BUG-13

- [ ] **P6-10: (Post-release, optional) Extra distribution channels**
  - Category: Distribution · Priority: P3 · Status: Not started · Depends on: P6-03 stable for ≥1 minor release
  - Acceptance: re-evaluate a Homebrew/Scoop formula and a CI Docker image based on user demand.
  - Evidence: audit §11
