"""Tests for project context readers: dependencies, .env parsing, git history."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from opspilot.context.deployment_history import get_changed_files, get_recent_commits
from opspilot.context.deps import read_dependencies
from opspilot.context.env import (
    find_env_references,
    find_undefined_env_vars,
    parse_env_content,
    read_env_names,
)

MANIFESTS = {
    "requirements.txt": "flask==3.0.0\n# comment\n-r other.txt\nrequests>=2.31\n"
    "git+https://github.com/x/y.git#egg=mylib\n",
    "Pipfile": '[packages]\nflask = "*"\n\n[dev-packages]\npytest = "*"\n',
    "pyproject.toml": '[project]\nname="x"\ndependencies = [\n  "typer>=0.12",\n]\n',
    "package.json": '{"dependencies":{"express":"^4.18.0"},"devDependencies":{"jest":"^29"}}',
    "Gemfile": "source 'https://rubygems.org'\ngem 'rails', '~> 7.1'\ngem 'pg'\n",
    "go.mod": "module x\n\ngo 1.22\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.1\n)\n",
    "Cargo.toml": '[dependencies]\nserde = "1.0"\ntokio = { version = "1", features = ["full"] }\n'
    '\n[dev-dependencies]\ncriterion = "0.5"\n',
    "pom.xml": "<project><dependencies><dependency><groupId>org.springframework</groupId>"
    "<artifactId>spring-core</artifactId><version>6.1.0</version></dependency>"
    "</dependencies></project>",
    "build.gradle": "dependencies {\n    implementation 'com.google.guava:guava:33.0.0-jre'\n"
    '    testImplementation("junit:junit:4.13.2")\n}\n',
}


def test_dependencies_from_every_supported_manifest(tmp_path: Path) -> None:
    for name, content in MANIFESTS.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    deps = read_dependencies(str(tmp_path))
    for expected in [
        "[python] flask==3.0.0",
        "[python] requests>=2.31",
        "[python] mylib",
        "[python] (dev) pytest",
        "[python] typer>=0.12",
        "[node] express@^4.18.0",
        "[node] (dev) jest@^29",
        "[ruby] rails (~> 7.1)",
        "[go] github.com/gin-gonic/gin@v1.9.1",
        "[rust] serde@1.0",
        "[rust] tokio@1",
        "[rust] (dev) criterion@0.5",
        "[java] org.springframework:spring-core@6.1.0",
        "[java] com.google.guava:guava:33.0.0-jre",
        "[java] junit:junit:4.13.2",
    ]:
        assert expected in deps, expected
    assert not any(d.startswith("[python] -r") for d in deps)


def test_malformed_manifest_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert read_dependencies(str(tmp_path)) == []


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("A=1", {"A": "1"}),
        ("export B=two", {"B": "two"}),
        ('C="quoted value"', {"C": "quoted value"}),
        ("D='single'", {"D": "single"}),
        ("E=has=equals", {"E": "has=equals"}),
        ("F=value # comment", {"F": "value"}),
        ("# comment\n\nG=1", {"G": "1"}),
        ('H="line1\nline2"', {"H": "line1\nline2"}),
        ("1BAD=x\nbad-name=y", {}),
    ],
)
def test_env_parser(content: str, expected: dict) -> None:
    assert parse_env_content(content) == expected


def test_env_names_merge_all_env_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("B=2\n", encoding="utf-8")
    assert read_env_names(str(tmp_path)) == ["A", "B"]


def test_env_reference_scan_prunes_dependency_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        "const u = process.env.API_URL;\nconst k = process.env['API_KEY'];\n",
        encoding="utf-8",
    )
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text(
        "process.env.FROM_DEPENDENCY", encoding="utf-8"
    )
    (tmp_path / ".env").write_text("API_URL=x\n", encoding="utf-8")
    assert find_env_references(str(tmp_path)) == {
        "API_URL": "src/app.ts",
        "API_KEY": "src/app.ts",
    }
    assert find_undefined_env_vars(str(tmp_path)) == {"API_KEY": "src/app.ts"}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_recent_commits_and_changed_files(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Dev",
        "GIT_AUTHOR_EMAIL": "dev@example.invalid",
        "GIT_COMMITTER_NAME": "Dev",
        "GIT_COMMITTER_EMAIL": "dev@example.invalid",
        "GIT_CEILING_DIRECTORIES": str(tmp_path.parent),
    }

    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True
        )

    git("init", "-q")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "app.py")
    git("commit", "-q", "-m", "Add app | with pipe")
    commits = get_recent_commits(str(tmp_path), since_hours=1)
    assert len(commits) == 1
    assert commits[0]["message"] == "Add app | with pipe"
    assert commits[0]["author"] == "Dev"
    assert get_changed_files(str(tmp_path), commits[0]["hash"]) == ["app.py"]


def test_recent_commits_outside_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert get_recent_commits(str(tmp_path / "missing"), since_hours=1) == []
