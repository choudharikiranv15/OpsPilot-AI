"""Deployment and Git history correlation for incident analysis."""

import logging
import subprocess
from datetime import datetime, timedelta

log = logging.getLogger("opspilot.git")


def get_recent_commits(
    repo_path: str, since_hours: int = 24, limit: int = 20
) -> list[dict]:
    """
    Get recent Git commits with metadata.

    Args:
        repo_path: Path to Git repository
        since_hours: Get commits from last N hours (default: 24)
        limit: Max number of commits to retrieve (default: 20)

    Returns:
        List of commit dictionaries with hash, author, date, message
    """
    try:
        since_time = datetime.now() - timedelta(hours=since_hours)
        since_str = since_time.strftime("%Y-%m-%d %H:%M:%S")

        # Git log format: hash|author|date|subject
        cmd = [
            "git",
            "-C",
            repo_path,
            "log",
            f"--since={since_str}",
            f"-{limit}",
            "--pretty=format:%H|%an|%ai|%s",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            log.debug(f"Git log failed: {result.stderr}")
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append(
                    {
                        "hash": parts[0][:8],  # Short hash
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3],
                    }
                )

        return commits

    except subprocess.TimeoutExpired:
        log.debug("Git log timed out")
        return []
    except FileNotFoundError:
        log.debug("Git not found. Install from: https://git-scm.com/")
        return []
    except Exception as e:
        log.debug(f"Failed to get Git commits: {e}")
        return []


def get_changed_files(repo_path: str, commit_hash: str) -> list[str]:
    """
    Get list of files changed in a specific commit.

    Args:
        repo_path: Path to Git repository
        commit_hash: Commit hash

    Returns:
        List of file paths changed in the commit
    """
    try:
        cmd = [
            "git",
            "-C",
            repo_path,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit_hash,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            return [f.strip() for f in result.stdout.split("\n") if f.strip()]
        else:
            return []

    except Exception:
        return []
