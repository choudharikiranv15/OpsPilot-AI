# Releasing

Releases are published to PyPI by GitHub Actions when a `v*` tag is pushed, using **PyPI Trusted Publishing** (OIDC). No API token is stored in the repository.

## One-time setup (maintainer)

1. On pypi.org, open the `opspilot-ai` project, go to **Publishing**, and add a trusted publisher:
   - Owner `choudharikiranv15`, repository `OpsPilot-AI`
   - Workflow `ci.yml`, environment `pypi`
2. In GitHub, go to **Settings → Environments** and create an environment named `pypi`. Optionally require a reviewer.
3. Delete the old `PYPI_API_TOKEN` repository secret if it exists.
4. Optional, for dry runs: add the same trusted publisher on test.pypi.org.

## Release checklist

1. Make sure `main` is green in CI.
2. Update `CHANGELOG.md`: rename `[Unreleased]` to the version and date.
3. Set `version` in `pyproject.toml` (e.g. `0.2.0`; use `0.2.0rc1` for a release candidate).
4. Commit: `chore(release): 0.2.0`.
5. Tag and push:

   ```bash
   git tag -a v0.2.0 -m "OpsPilot 0.2.0"
   git push origin v0.2.0
   ```

6. CI runs lint, tests, clean-install smoke tests and security scans, then publishes `dist/*` to PyPI.
7. Create a GitHub Release from the tag, with the changelog section as notes.
8. Verify on Windows, macOS and Linux:

   ```bash
   pipx install opspilot-ai==0.2.0
   opspilot --version && opspilot doctor
   ```

9. Bump `pyproject.toml` to the next `.dev0` version.

## Release candidate dry run (TestPyPI)

Build locally and upload a release candidate to TestPyPI with your own credentials:

```bash
python -m build
twine check --strict dist/*
twine upload --repository testpypi dist/*
pipx install --index-url https://test.pypi.org/simple/ \
  --pip-args="--extra-index-url https://pypi.org/simple/" opspilot-ai==0.2.0rc1
```

PyPI never accepts the same version twice. If something is wrong after publishing, release a new patch version; yank the bad one only if it is harmful.
