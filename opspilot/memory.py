import json
from pathlib import Path

MEMORY_FILE = Path.home() / ".opspilot_memory.json"


def load_memory() -> list[dict]:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return []


def save_memory(entry: dict):
    memory = load_memory()
    memory.append(entry)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2))


def find_similar_issues(project_root: str, threshold: float = 0.6):
    memory = load_memory()
    return [
        m
        for m in memory
        if m["project"] == project_root and m["confidence"] >= threshold
    ]
