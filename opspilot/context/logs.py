"""Log file reading and aggregation for local project logs."""

from pathlib import Path
from typing import Optional, List
from opspilot.constants import LOG_TRUNCATE_LIMIT, LOG_FILE_PATTERNS


def read_logs(project_root: str, max_size: int = LOG_TRUNCATE_LIMIT) -> Optional[str]:
    """
    Read and aggregate log files from project directory.

    Searches in common log locations:
    - ./logs/
    - ./log/
    - ./var/log/
    - ./ (project root for common log files)

    Supports multiple patterns:
    - *.log, *.log.*, *.txt (in log dirs)
    - *.log.json, *.jsonl (structured logs)
    - Common named logs: app.log, error.log, debug.log, etc.

    Args:
        project_root: Root directory of the project
        max_size: Maximum characters to return (default from constants)

    Returns:
        Combined log content from most recent files, or None if no logs found
    """
    root = Path(project_root)
    log_files = []

    # Search in common log directories
    log_dirs = [
        root / "logs",
        root / "log",
        root / "var" / "log",
        root,  # Also check project root
    ]

    # Patterns to search for
    patterns = LOG_FILE_PATTERNS + [
        "app.log",
        "error.log",
        "debug.log",
        "server.log",
        "application.log",
        "output.log",
        "stderr.log",
        "stdout.log",
    ]

    # Collect all matching log files
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue

        for pattern in patterns:
            try:
                matches = list(log_dir.glob(pattern))
                # Filter out directories and very large files (>10MB)
                for f in matches:
                    if f.is_file() and f.stat().st_size < 10 * 1024 * 1024:
                        log_files.append(f)
            except (PermissionError, OSError):
                continue

    if not log_files:
        return None

    # Remove duplicates and sort by modification time (most recent first)
    log_files = list(set(log_files))
    log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    # Read and combine logs, prioritizing recent files
    combined_logs = []
    total_size = 0
    files_read = 0

    for log_file in log_files:
        if total_size >= max_size or files_read >= 5:  # Max 5 files
            break

        try:
            content = log_file.read_text(errors="ignore")
            # Take the last portion if file is large
            if len(content) > max_size // 2:
                content = content[-(max_size // 2):]

            remaining_space = max_size - total_size
            if len(content) > remaining_space:
                content = content[-remaining_space:]

            combined_logs.append(f"=== {log_file.name} ===\n{content}")
            total_size += len(content) + len(log_file.name) + 10
            files_read += 1

        except (PermissionError, OSError, UnicodeDecodeError):
            continue

    if not combined_logs:
        return None

    return "\n\n".join(combined_logs)


def find_log_files(project_root: str) -> List[Path]:
    """
    Find all log files in the project.

    Returns:
        List of Path objects for log files found
    """
    root = Path(project_root)
    log_files = []

    log_dirs = [
        root / "logs",
        root / "log",
        root / "var" / "log",
        root,
    ]

    for log_dir in log_dirs:
        if not log_dir.exists():
            continue

        for pattern in LOG_FILE_PATTERNS:
            try:
                matches = list(log_dir.glob(pattern))
                log_files.extend([f for f in matches if f.is_file()])
            except (PermissionError, OSError):
                continue

    return list(set(log_files))


def get_log_summary(project_root: str) -> dict:
    """
    Get summary of available log files.

    Returns:
        Dictionary with log file information
    """
    log_files = find_log_files(project_root)

    if not log_files:
        return {"found": False, "files": [], "total_size": 0}

    file_info = []
    total_size = 0

    for f in log_files:
        try:
            size = f.stat().st_size
            mtime = f.stat().st_mtime
            file_info.append({
                "name": f.name,
                "path": str(f),
                "size": size,
                "modified": mtime,
            })
            total_size += size
        except (PermissionError, OSError):
            continue

    # Sort by modification time
    file_info.sort(key=lambda x: x["modified"], reverse=True)

    return {
        "found": True,
        "files": file_info,
        "total_size": total_size,
        "count": len(file_info),
    }
