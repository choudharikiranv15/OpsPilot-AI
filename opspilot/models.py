"""Data models for analysis results (also the --json / report schema).

``AnalysisResult.model_dump(mode="json")`` is the stable machine-readable
output. Bump ``SCHEMA_VERSION`` on breaking changes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1"

FactKind = Literal[
    "build_error", "log_error", "stack_frame", "log_summary", "config", "change"
]


class Fact(BaseModel):
    """A deterministic observation extracted from the inputs (never AI-generated)."""

    id: str
    kind: FactKind
    text: str
    source: str
    count: int = 1
    location: str | None = Field(
        default=None, description="'path:line' inside the project, when known"
    )


class Hypothesis(BaseModel):
    """An AI-generated explanation, with the facts it cites."""

    cause: str
    category: str = "other"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list, description="Cited fact IDs")
    supported: bool = Field(
        default=False, description="True when it cites at least one real fact"
    )


class Diagnosis(BaseModel):
    summary: str = ""
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    """A dry-run patch proposal. OpsPilot never applies it."""

    file: str
    diff: str
    rationale: str = ""
    check: Literal["applies", "does_not_apply", "not_checked"] = "not_checked"


class LLMUsage(BaseModel):
    provider: str
    model: str | None
    location: Literal["local", "cloud"]
    requests: int
    redactions: int


class AnalysisResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    opspilot_version: str
    timestamp: str
    project: str
    mode: Literal["diagnose", "facts_only"]
    inputs: list[str] = Field(default_factory=list)
    severity: str | None = None
    facts: list[Fact] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)
    seen_before: list[dict] = Field(default_factory=list)
    llm: LLMUsage | None = None
    warnings: list[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
