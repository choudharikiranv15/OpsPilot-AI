"""Deployment and Git history correlation for incident analysis."""

import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path


def get_recent_commits(repo_path: str, since_hours: int = 24, limit: int = 20) -> List[Dict]:
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
            "git", "-C", repo_path, "log",
            f"--since={since_str}",
            f"-{limit}",
            "--pretty=format:%H|%an|%ai|%s"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            print(f"Git log failed: {result.stderr}")
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0][:8],  # Short hash
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3]
                })

        return commits

    except subprocess.TimeoutExpired:
        print("Git log timed out")
        return []
    except FileNotFoundError:
        print("Git not found. Install from: https://git-scm.com/")
        return []
    except Exception as e:
        print(f"Failed to get Git commits: {e}")
        return []


def get_changed_files(repo_path: str, commit_hash: str) -> List[str]:
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
            "git", "-C", repo_path, "diff-tree",
            "--no-commit-id", "--name-only", "-r",
            commit_hash
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return [f.strip() for f in result.stdout.split("\n") if f.strip()]
        else:
            return []

    except Exception:
        return []


def correlate_with_error_timeline(commits: List[Dict], error_first_seen: str) -> Dict:
    """
    Correlate commits with error timeline.

    Identifies commits that happened around the same time as errors appeared.

    Args:
        commits: List of commit dictionaries
        error_first_seen: Timestamp when error was first seen

    Returns:
        Analysis dictionary with suspicious commits
    """
    try:
        # Parse error timestamp (supports common formats)
        error_time = None
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                error_time = datetime.strptime(error_first_seen[:19], fmt)
                break
            except ValueError:
                continue

        if not error_time:
            return {"correlation": "unknown", "reason": "Could not parse error timestamp"}

        # Find commits within ±2 hours of error
        suspicious_commits = []
        for commit in commits:
            try:
                commit_time = datetime.strptime(commit["date"][:19], "%Y-%m-%d %H:%M:%S")
                time_diff = abs((commit_time - error_time).total_seconds() / 3600)

                if time_diff <= 2:
                    suspicious_commits.append({
                        **commit,
                        "time_diff_hours": round(time_diff, 1)
                    })
            except ValueError:
                continue

        if suspicious_commits:
            return {
                "correlation": "strong",
                "suspicious_commits": suspicious_commits,
                "count": len(suspicious_commits),
                "reason": f"Found {len(suspicious_commits)} commits within 2 hours of error"
            }
        else:
            return {
                "correlation": "weak",
                "reason": "No commits near error occurrence time"
            }

    except Exception as e:
        return {"correlation": "error", "reason": str(e)}


def analyze_deployment_impact(repo_path: str, since_hours: int = 24) -> Dict:
    """
    Analyze recent deployments and their potential impact.

    Args:
        repo_path: Path to Git repository
        since_hours: Analyze last N hours (default: 24)

    Returns:
        Deployment analysis with commits, changed files, and risk assessment
    """
    commits = get_recent_commits(repo_path, since_hours)

    if not commits:
        return {
            "has_recent_changes": False,
            "commits": [],
            "risk_level": "LOW",
            "reason": f"No commits in the last {since_hours} hours"
        }

    # Categorize changed files
    all_changed_files = []
    high_risk_files = []
    config_files = []

    for commit in commits:
        files = get_changed_files(repo_path, commit["hash"])
        all_changed_files.extend(files)

        # Identify high-risk changes
        for file in files:
            file_lower = file.lower()

            # Config files
            if any(x in file_lower for x in [".env", "config", "settings", "docker"]):
                config_files.append({"file": file, "commit": commit["hash"]})

            # Database migrations
            if "migration" in file_lower or "schema" in file_lower:
                high_risk_files.append({"file": file, "commit": commit["hash"], "reason": "Database change"})

            # Critical services
            if any(x in file_lower for x in ["auth", "payment", "api", "gateway"]):
                high_risk_files.append({"file": file, "commit": commit["hash"], "reason": "Critical service"})

    # Assess risk level
    if high_risk_files:
        risk_level = "HIGH"
        reason = f"{len(high_risk_files)} high-risk files changed (migrations, auth, payments)"
    elif config_files:
        risk_level = "MEDIUM"
        reason = f"{len(config_files)} configuration files changed"
    elif len(commits) > 10:
        risk_level = "MEDIUM"
        reason = f"High deployment frequency ({len(commits)} commits)"
    else:
        risk_level = "LOW"
        reason = f"{len(commits)} commits with standard changes"

    return {
        "has_recent_changes": True,
        "commits": commits,
        "total_commits": len(commits),
        "changed_files_count": len(set(all_changed_files)),
        "high_risk_files": high_risk_files,
        "config_files": config_files,
        "risk_level": risk_level,
        "reason": reason
    }


def get_blame_for_error(repo_path: str, file_path: str, line_number: int) -> Optional[Dict]:
    """
    Get Git blame information for a specific line.

    Args:
        repo_path: Path to Git repository
        file_path: File path relative to repo root
        line_number: Line number (1-indexed)

    Returns:
        Blame info with commit hash, author, date
    """
    try:
        cmd = [
            "git", "-C", repo_path, "blame",
            "-L", f"{line_number},{line_number}",
            "--porcelain",
            file_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return None

        # Parse porcelain format
        lines = result.stdout.split("\n")
        if not lines:
            return None

        # First line: hash original_line final_line num_lines
        parts = lines[0].split()
        commit_hash = parts[0] if parts else "unknown"

        # Extract author and date from subsequent lines
        author = "unknown"
        date = "unknown"

        for line in lines[1:]:
            if line.startswith("author "):
                author = line[7:]
            elif line.startswith("author-time "):
                try:
                    timestamp = int(line[12:])
                    date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

        return {
            "commit": commit_hash[:8],
            "author": author,
            "date": date,
            "file": file_path,
            "line": line_number
        }

    except Exception:
        return None


def format_deployment_analysis(analysis: Dict) -> str:
    """
    Format deployment analysis as human-readable text.

    Args:
        analysis: Deployment analysis dictionary

    Returns:
        Formatted multi-line string
    """
    if not analysis.get("has_recent_changes"):
        return "\nNo recent deployments detected.\n"

    output = []

    output.append("\n" + "=" * 60)
    output.append("RECENT DEPLOYMENT ANALYSIS")
    output.append("=" * 60)

    risk_level = analysis.get("risk_level", "UNKNOWN")
    risk_color_map = {
        "HIGH": "RED",
        "MEDIUM": "YELLOW",
        "LOW": "GREEN"
    }

    output.append(f"\nRisk Level: {risk_level}")
    output.append(f"Reason: {analysis.get('reason', 'N/A')}")
    output.append(f"\nTotal Commits: {analysis.get('total_commits', 0)}")
    output.append(f"Files Changed: {analysis.get('changed_files_count', 0)}")

    if analysis.get("high_risk_files"):
        output.append(f"\nHigh-Risk Changes ({len(analysis['high_risk_files'])}):")
        for item in analysis["high_risk_files"][:5]:  # Show first 5
            output.append(f"  - {item['file']} ({item['reason']}) [{item['commit']}]")

    if analysis.get("config_files"):
        output.append(f"\nConfiguration Changes ({len(analysis['config_files'])}):")
        for item in analysis["config_files"][:5]:
            output.append(f"  - {item['file']} [{item['commit']}]")

    if analysis.get("commits"):
        output.append(f"\nRecent Commits:")
        for commit in analysis["commits"][:5]:
            output.append(f"  [{commit['hash']}] {commit['message']}")
            output.append(f"    by {commit['author']} at {commit['date']}")

    return "\n".join(output)
