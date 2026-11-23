"""Log file reading and aggregation for local project logs."""

from pathlib import Path

from opspilot.constants import LOG_FILE_PATTERNS, LOG_TRUNCATE_LIMIT


def read_logs(project_root: str, max_size: int = LOG_TRUNCATE_LIMIT) -> str | None:
    """
    Read and aggregate log files from project directory with intelligent sampling.

    Searches in common log locations:
    - ./logs/
    - ./log/
    - ./var/log/
    - ./ (project root for common log files)

    Performance optimizations for large codebases:
    - Skips files > 50MB (likely rotated logs)
    - Reads max 5 files
    - Prioritizes recent files
    - Samples errors intelligently instead of full content

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
                # Filter out directories and very large files (>50MB for performance)
                for f in matches:
                    if f.is_file():
                        size = f.stat().st_size
                        # Skip very large files (likely old rotated logs)
                        if size < 50 * 1024 * 1024:
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
            file_size = log_file.stat().st_size

            # For large files (>1MB), sample intelligently instead of reading all
            if file_size > 1024 * 1024:  # 1MB
                content = _sample_large_log(log_file, max_size // 5)
            else:
                content = log_file.read_text(errors="ignore")
                # Take the last portion if file is large
                if len(content) > max_size // 2:
                    content = content[-(max_size // 2) :]

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


def _sample_large_log(log_file: Path, max_lines: int = 200) -> str:
    """
    Intelligently sample a large log file, prioritizing errors.

    Strategy:
    1. Sample last N lines (most recent)
    2. Prioritize lines with ERROR, FATAL, Exception
    3. Skip repetitive lines

    Args:
        log_file: Path to log file
        max_lines: Maximum lines to sample

    Returns:
        Sampled log content
    """
    try:
        # Read last N lines using efficient tail-like approach
        with open(log_file, "rb") as f:
            # Seek to end
            f.seek(0, 2)
            file_size = f.tell()

            # Read last chunk (up to 100KB for performance)
            chunk_size = min(100 * 1024, file_size)
            f.seek(max(0, file_size - chunk_size))

            content = f.read().decode("utf-8", errors="ignore")
            lines = content.splitlines()

            # Prioritize error lines
            error_keywords = [
                "ERROR",
                "FATAL",
                "CRITICAL",
                "Exception",
                "Traceback",
                "Failed",
                "Timeout",
            ]
            error_lines = []
            other_lines = []

            for line in lines[-max_lines:]:
                if any(keyword in line for keyword in error_keywords):
                    error_lines.append(line)
                else:
                    other_lines.append(line)

            # Take all errors + some context
            sampled = error_lines[: max_lines // 2] + other_lines[: max_lines // 2]

            if len(lines) > max_lines:
                return f"[Sampled {len(sampled)} of {len(lines)} lines]\n" + "\n".join(
                    sampled
                )
            return "\n".join(sampled)

    except Exception:
        return "[Failed to sample log file]"


def find_log_files(project_root: str) -> list[Path]:
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
            file_info.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size": size,
                    "modified": mtime,
                }
            )
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
