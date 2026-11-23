"""Local history of past diagnoses ("seen before" hints).

Stored in ``~/.opspilot_memory.json``. Only minimal fields are kept (project
path, time, hypothesis, and an error fingerprint) - never raw logs or
evidence. Writes are atomic, the file is capped at ``MEMORY_MAX_ENTRIES``,
and a corrupt file is moved aside instead of breaking every run.

Delete the file at any time to clear the history.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from opspilot.constants import MEMORY_MAX_ENTRIES

log = logging.getLogger("opspilot.memory")

MEMORY_FILE = Path.home() / ".opspilot_memory.json"
_FIELDS = ("project", "timestamp", "hypothesis", "fingerprint", "signals")


def error_signals(evidence: dict[str, Any]) -> list[str]:
    """Stable, low-sensitivity signals describing the errors in ``evidence``."""
    patterns = evidence.get("error_patterns") or {}
    build = evidence.get("build_errors") or {}
    signals: set[str] = set()
    signals.update(str(e) for e in patterns.get("exceptions", []))
    signals.update(f"http:{code}" for code in patterns.get("http_errors", {}))
    signals.update(str(e) for e in patterns.get("database_errors", []))
    signals.update(f"build:{t}" for t in build.get("error_types", []))
    return sorted(signals)


def fingerprint(evidence: dict[str, Any]) -> str | None:
    signals = error_signals(evidence)
    if not signals:
        return None
    return hashlib.sha256("|".join(signals).encode()).hexdigest()[:16]


def load_memory() -> list[dict[str, Any]]:
    """Load valid history entries; quarantine an unreadable file."""
    path = MEMORY_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _quarantine(path, e)
        return []
    if not isinstance(data, list):
        _quarantine(path, ValueError("not a list"))
        return []
    return [_minimal(e) for e in data if isinstance(e, dict) and e.get("project")]


def save_memory(project_root: str, hypothesis: str | None, evidence: dict) -> None:
    """Append a minimal entry for this run (best effort; never raises)."""
    entry = {
        "project": project_root,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "hypothesis": hypothesis,
        "fingerprint": fingerprint(evidence),
        "signals": error_signals(evidence)[:20],
    }
    entries = (load_memory() + [entry])[-MEMORY_MAX_ENTRIES:]
    try:
        _atomic_write(MEMORY_FILE, json.dumps(entries, indent=2))
    except OSError as e:
        log.warning("could not update history file %s: %s", MEMORY_FILE, e)


def find_similar_issues(
    project_root: str, evidence: dict | None = None, limit: int = 3
) -> list[dict[str, Any]]:
    """
    Past diagnoses for this project, most recent first.

    When ``evidence`` is given, only entries with the same error fingerprint
    are returned.
    """
    wanted = fingerprint(evidence) if evidence is not None else None
    matches = [
        e
        for e in load_memory()
        if e.get("project") == project_root
        and e.get("hypothesis")
        and (wanted is None or e.get("fingerprint") == wanted)
    ]
    return list(reversed(matches))[:limit]


def _minimal(entry: dict[str, Any]) -> dict[str, Any]:
    minimal = {k: entry.get(k) for k in _FIELDS}
    if minimal["fingerprint"] is None and isinstance(entry.get("evidence"), dict):
        # Upgrade entries written by older versions (which stored full evidence).
        minimal["fingerprint"] = fingerprint(entry["evidence"])
        minimal["signals"] = error_signals(entry["evidence"])[:20]
    return minimal


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".opspilot_memory.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _quarantine(path: Path, error: Exception) -> None:
    target = path.with_name(
        f"{path.name}.corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    try:
        os.replace(path, target)
        log.warning("history file was unreadable (%s); moved to %s", error, target)
    except OSError:
        log.warning("history file %s is unreadable (%s); ignoring it", path, error)
