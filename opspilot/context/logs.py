from pathlib import Path
from typing import Optional


def read_logs(project_root: str) -> Optional[str]:
    logs_dir = Path(project_root) / "logs"
    if not logs_dir.exists():
        return None

    log_files = list(logs_dir.glob("*.log"))
    if not log_files:
        return None

    # Read most recent log file
    latest_log = max(log_files, key=lambda f: f.stat().st_mtime)
    return latest_log.read_text(errors="ignore")[-5000:]
