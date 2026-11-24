# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report them privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability** (GitHub private vulnerability reporting).

Please include:

- the OpsPilot version (`opspilot --version`) and operating system,
- what an attacker controls (for example: log content, a cloned repository, a remote log endpoint),
- steps to reproduce, and the impact you observed.

You should receive an acknowledgement within 7 days. Fixes are released as patch versions and credited in the changelog unless you prefer otherwise.

## Supported versions

Only the latest release receives security fixes while OpsPilot is in the 0.x series.

## Security model (summary)

OpsPilot is a local command-line tool that runs with your privileges. Its main safeguards:

- It never executes model output and never writes to your project. Patches are dry-run only.
- Subprocesses (`git`, `aws`, `kubectl`, `--build-cmd`) run without a shell, with bounded output and time limits.
- Log, file and model text is treated as untrusted. It is rendered literally in the terminal and delimited in prompts.
- `.env` values are never read into output or prompts. Likely secrets are redacted before text is sent to a model.
- Data goes only to local Ollama unless you explicitly opt in to a cloud provider.

Known limitations: redaction is pattern-based and can miss unusual secret formats, and content in logs can still try to steer the model's answer (prompt injection). That is why output is advisory and cloud use is opt-in. See the Privacy section of the [README](README.md#privacy).
