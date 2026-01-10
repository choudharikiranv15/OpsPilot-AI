from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class AgentState:
    project_root: str
    context: Dict[str, Any] = field(default_factory=dict)

    hypothesis: Optional[str] = None
    confidence: float = 0.0

    evidence: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[Dict[str, Any]] = field(default_factory=list)

    iteration: int = 0
    max_iterations: int = 2

    terminated: bool = False
