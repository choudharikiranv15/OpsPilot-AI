"""Local log discovery and bounded reading.

Only ``*.log`` files (and numbered rotations such as ``app.log.1``) in
``./logs``, ``./log``, ``./var/log`` and the project root are picked up
automatically. Other files must be passed explicitly with ``--log-source``.
Every read is a bounded tail read, so large files cannot exhaust memory.
"""

from __future__ import annotations

import os
from pathlib import Path

from opspilot.constants import LOG_TRUNCATE_LIMIT

LOG_DIRS = ("logs", "log", os.path.join("var", "log"), ".")
LOG_FILE_PATTERNS = ("*.log", "*.log.[0-9]", "*.log.[0-9][0-9]")
MAX_LOG_FILES = 5
TAIL_BYTES_PER_FILE = 256 * 1024


def find_log_files(project_root: str) -> list[Path]:
    """Return discoverable log files, most recently modified first."""
    root = Path(project_root)
    found: dict[Path, float] = {}
    for rel in LOG_DIRS:
        directory = (root / rel).resolve()
        if not directory.is_dir():
            continue
        for pattern in LOG_FILE_PATTERNS:
            try:
                for path in directory.glob(pattern):
                    if path.is_file():
                        found[path] = path.stat().st_mtime
            except OSError:
                continue
    return sorted(found, key=found.__getitem__, reverse=True)


def read_tail(path: Path, max_bytes: int) -> str:
    """Read at most the last ``max_bytes`` of a file, starting at a line boundary."""
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - max_bytes)
        handle.seek(start)
        data = handle.read(max_bytes)
    text = data.decode("utf-8", errors="replace")
    if start > 0 and "\n" in text:
        text = text.split("\n", 1)[1]
    return text


def read_logs(project_root: str, max_size: int = LOG_TRUNCATE_LIMIT) -> str | None:
    """
    Combine the tails of the most recent local log files.

    Newer files come first. The result is at most roughly ``max_size``
    characters; each file contributes its most recent lines.
    """
    files = find_log_files(project_root)[:MAX_LOG_FILES]
    if not files:
        return None
    budget = max(1, max_size // len(files))
    sections = []
    for path in files:
        try:
            content = read_tail(path, TAIL_BYTES_PER_FILE)
        except OSError:
            continue
        if len(content) > budget:
            content = content[-budget:]
            if "\n" in content:
                content = content.split("\n", 1)[1]
        rel = _relative(path, project_root)
        sections.append(f"=== {rel} ===\n{content.rstrip()}")
    return "\n\n".join(sections) if sections else None


def _relative(path: Path, project_root: str) -> str:
    try:
        return path.relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return path.name
