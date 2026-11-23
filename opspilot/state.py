from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    project_root: str
    context: dict[str, Any] = field(default_factory=dict)

    hypothesis: str | None = None
    confidence: float = 0.0

    evidence: dict[str, Any] = field(default_factory=dict)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    checks_remaining: list[str] = field(default_factory=list)

    iteration: int = 0
    max_iterations: int = 2

    terminated: bool = False
