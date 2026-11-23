"""
Runbook detection and matching for organizational knowledge.

Searches for runbooks in common locations and matches errors to existing solutions.
"""

import re
from pathlib import Path

RUNBOOK_LOCATIONS = [
    "docs/runbooks",
    ".runbooks",
    "runbooks",
    "docs/incident-response",
    "wiki/runbooks",
    "ops/runbooks",
]

RUNBOOK_EXTENSIONS = [".md", ".yaml", ".yml", ".txt"]


def find_runbooks(project_root: str) -> list[dict]:
    """
    Find all runbooks in the project.

    Returns list of runbooks with metadata:
    - path: File path
    - title: Runbook title
    - keywords: Extracted keywords
    - symptoms: Described symptoms
    """
    root = Path(project_root)
    runbooks = []

    for location in RUNBOOK_LOCATIONS:
        runbook_dir = root / location
        if not runbook_dir.exists():
            continue

        for ext in RUNBOOK_EXTENSIONS:
            for runbook_file in runbook_dir.rglob(f"*{ext}"):
                if runbook_file.is_file():
                    try:
                        runbook_data = parse_runbook(runbook_file)
                        if runbook_data:
                            runbooks.append(runbook_data)
                    except Exception:
                        continue

    return runbooks


def parse_runbook(file_path: Path) -> dict | None:
    """
    Parse runbook file to extract metadata.

    Looks for:
    - Title (# heading or filename)
    - Keywords (tags, labels)
    - Symptoms (## Symptoms, ## Detection)
    - Resolution steps (## Resolution, ## Fix)
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    # Extract title
    title = None
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = file_path.stem.replace("-", " ").replace("_", " ").title()

    # Extract keywords
    keywords = []

    # Look for tags/labels
    tags_match = re.search(
        r"(?:tags|labels|keywords):\s*\[(.+?)\]", content, re.IGNORECASE
    )
    if tags_match:
        keywords = [k.strip().strip("\"'") for k in tags_match.group(1).split(",")]

    # Extract from title and content
    keywords.extend(extract_keywords_from_text(title))
    keywords.extend(extract_keywords_from_text(content[:500]))  # First 500 chars

    keywords = list(set(keywords))  # Remove duplicates

    # Extract symptoms section
    symptoms = extract_section(content, ["Symptoms", "Detection", "How to Detect"])

    # Extract resolution section
    resolution = extract_section(
        content, ["Resolution", "Fix", "Remediation", "Solution"]
    )

    return {
        "path": str(file_path),
        "title": title,
        "keywords": keywords,
        "symptoms": symptoms or "",
        "resolution": resolution or "",
        "content_preview": content[:200],
    }


def extract_section(content: str, section_headers: list[str]) -> str | None:
    """Extract content under specific section headers."""
    for header in section_headers:
        # Match markdown headers
        pattern = rf"^##\s+{header}\s*$(.+?)(?=^##\s|\Z)"
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()[:500]  # First 500 chars
    return None


def extract_keywords_from_text(text: str) -> list[str]:
    """
    Extract meaningful keywords from text.

    Looks for technical terms like:
    - Service names (redis, postgres, kafka)
    - Error types (timeout, connection, memory)
    - Operations (restart, scale, rollback)
    """
    if not text:
        return []

    text_lower = text.lower()
    keywords = []

    # Technical terms dictionary
    tech_keywords = [
        # Services
        "redis",
        "postgres",
        "mysql",
        "mongodb",
        "kafka",
        "rabbitmq",
        "elasticsearch",
        "nginx",
        "apache",
        "docker",
        "kubernetes",
        # Error types
        "timeout",
        "connection",
        "memory",
        "disk",
        "cpu",
        "network",
        "deadlock",
        "leak",
        "crash",
        "hang",
        "slow",
        "error",
        # Operations
        "restart",
        "scale",
        "rollback",
        "deploy",
        "migrate",
        "backup",
        # Severity
        "p0",
        "p1",
        "critical",
        "urgent",
        "high",
        "sev1",
        "sev2",
    ]

    for keyword in tech_keywords:
        if keyword in text_lower:
            keywords.append(keyword)

    return keywords


def match_error_to_runbook(
    error_patterns: dict,
    error_logs: list[str],
    runbooks: list[dict],
    min_match_score: float = 0.3,
) -> list[dict]:
    """
    Match current errors to existing runbooks.

    Args:
        error_patterns: Detected error patterns (from pattern_analysis)
        error_logs: Raw error log lines
        runbooks: List of parsed runbooks
        min_match_score: Minimum score to consider a match

    Returns:
        List of matching runbooks with scores
    """
    if not runbooks:
        return []

    # Extract keywords from current errors
    error_keywords = set()

    # From error patterns
    if error_patterns.get("exceptions"):
        error_keywords.update(k.lower() for k in error_patterns["exceptions"])

    # From error logs
    error_text = " ".join(error_logs[:50]).lower()  # First 50 lines
    error_keywords.update(extract_keywords_from_text(error_text))

    # Add error types
    if error_patterns.get("http_errors"):
        error_keywords.add("http")
        error_keywords.add("api")
    if error_patterns.get("timeout_errors"):
        error_keywords.add("timeout")
    if error_patterns.get("database_errors"):
        error_keywords.add("database")

    if not error_keywords:
        return []

    # Score each runbook
    matches = []
    for runbook in runbooks:
        score = calculate_match_score(error_keywords, runbook)

        if score >= min_match_score:
            matches.append(
                {
                    **runbook,
                    "match_score": score,
                    "matched_keywords": list(error_keywords & set(runbook["keywords"])),
                }
            )

    # Sort by score (highest first)
    matches.sort(key=lambda x: x["match_score"], reverse=True)

    return matches


def calculate_match_score(error_keywords: set, runbook: dict) -> float:
    """
    Calculate match score between error and runbook.

    Score based on:
    - Keyword overlap (60%)
    - Symptom similarity (30%)
    - Title relevance (10%)
    """
    runbook_keywords = set(runbook["keywords"])

    if not runbook_keywords:
        return 0.0

    # Keyword overlap
    overlap = error_keywords & runbook_keywords
    keyword_score = len(overlap) / max(len(error_keywords), len(runbook_keywords))

    # Symptom similarity (simple check if error keywords appear in symptoms)
    symptom_score = 0.0
    if runbook.get("symptoms"):
        symptoms_lower = runbook["symptoms"].lower()
        matches = sum(1 for kw in error_keywords if kw in symptoms_lower)
        symptom_score = min(matches / len(error_keywords), 1.0)

    # Title relevance
    title_score = 0.0
    if runbook.get("title"):
        title_lower = runbook["title"].lower()
        matches = sum(1 for kw in error_keywords if kw in title_lower)
        title_score = min(matches / len(error_keywords), 1.0)

    # Weighted average
    total_score = (keyword_score * 0.6) + (symptom_score * 0.3) + (title_score * 0.1)

    return total_score


def format_runbook_match(match: dict) -> str:
    """Format runbook match for display."""
    lines = [
        f"📖 Runbook: {match['title']}",
        f"   Match score: {match['match_score']:.1%}",
        f"   Matched keywords: {', '.join(match.get('matched_keywords', []))}",
        f"   Path: {match['path']}",
    ]

    if match.get("symptoms"):
        lines.append(f"   Symptoms: {match['symptoms'][:100]}...")

    return "\n".join(lines)
