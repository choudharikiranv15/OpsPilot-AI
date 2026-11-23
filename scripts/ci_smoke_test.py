"""Clean-install smoke test for a built OpsPilot wheel.

Creates a fresh virtualenv, installs the wheel with NO extras, and runs the
CLI against the sample fixture project. Fails if any step fails.

Usage: python scripts/ci_smoke_test.py <dist-dir>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample_project"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )
    print(result.stdout[-3000:])
    print(result.stderr[-3000:], file=sys.stderr)
    if result.returncode != 0:
        sys.exit(f"command failed with exit code {result.returncode}")
    return result


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        sys.exit(f"no wheel found in {dist}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        venv_dir = tmp_path / "venv"
        venv.create(venv_dir, with_pip=True)
        bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        python = str(bin_dir / "python")
        run([python, "-m", "pip", "install", "--quiet", str(wheels[-1])])
        opspilot = shutil.which("opspilot", path=str(bin_dir))
        if not opspilot:
            sys.exit("opspilot console script was not installed")

        project = tmp_path / "project"
        shutil.copytree(FIXTURE, project)
        home = tmp_path / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}

        run([opspilot, "--version"], env=env)
        run([opspilot, "--help"], env=env)
        run([opspilot, "analyze", "--help"], env=env)
        run([opspilot, "doctor", "--help"], env=env)
        run([python, "-m", "opspilot", "--help"], env=env)
        run([opspilot, "analyze", "--no-llm"], cwd=project, env=env)
        result = run([opspilot, "analyze", "--no-llm", "--json"], cwd=project, env=env)
        json.loads(result.stdout)  # stdout must be pure JSON

    print("smoke test passed")


if __name__ == "__main__":
    main()
