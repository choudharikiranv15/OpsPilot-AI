# OpsPilot Architecture

> High-level design documentation for the OpsPilot agentic AI system

---

## Table of Contents

- [Overview](#overview)
- [Core Principles](#core-principles)
- [System Architecture](#system-architecture)
- [Agent Design](#agent-design)
- [Data Flow](#data-flow)
- [State Management](#state-management)
- [LLM Integration](#llm-integration)
- [Design Decisions](#design-decisions)
- [Future Enhancements](#future-enhancements)

---

## Overview

OpsPilot implements a **multi-agent agentic architecture** where specialized AI agents collaborate to diagnose and resolve runtime issues. The system follows a clear workflow: gather context → generate hypothesis → verify with evidence → suggest fixes.

### Key Components

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│                      (User Interface)                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                 Multi-Provider LLM Router                    │
│   (Ollama → OpenRouter → Gemini → HuggingFace fallback)    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Graph Engine                              │
│              (Orchestrates Agent Workflow)                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┬──────────────┐
        │                   │                   │              │
        ▼                   ▼                   ▼              ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐ ┌──────────────┐
│   Planner    │───▶│  Verifier    │───▶│    Fixer     │─│ Remediation  │
│    Agent     │    │    Agent     │    │    Agent     │ │    Agent     │
└──────────────┘    └──────────────┘    └──────────────┘ └──────────────┘
        │                   │                   │              │
        └───────────────────┴───────────────────┴──────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│      Context Layer          │  │    Memory Layer (Redis)     │
│  • Local logs               │  │  • User-isolated storage    │
│  • Production logs (S3/K8s) │  │  • Auto-expiring TTL        │
│  • Environment vars         │  │  • Similarity search        │
│  • Dependencies             │  │  • Severity indexing        │
│  • Docker configs           │  │  • LLM health metrics       │
│  • Git deployment history   │  │  • Fallback to file-based   │
└─────────────────────────────┘  └─────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│                      Tools Layer                             │
│    • Pattern Analysis (P0/P1/P2/P3 classification)          │
│    • Log Error Analysis                                      │
│    • Environment Validation                                  │
│    • Dependency Checking                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Principles

### 1. **Safety First**
- All fix suggestions are **dry-run only**
- Never automatically applies changes to user's code
- Provides clear rationale for every suggestion

### 2. **Evidence-Based Reasoning**
- Decisions backed by concrete evidence (logs, configs, etc.)
- Confidence scoring (0.0 - 1.0) for transparency
- Threshold-based decision making (confidence ≥ 0.6 required for fixes)

### 3. **Modularity & Extensibility**
- Each agent is independent and focused
- Context modules are pluggable
- Easy to add new agents or data sources

### 4. **Privacy-Focused with High Availability**
- Prefers local LLM (Ollama) - no cloud dependencies by default
- Automatic fallback to cloud providers for reliability
- All cloud providers use FREE tiers (OpenRouter, Gemini, HuggingFace)
- User controls provider preference via environment variables

### 5. **Learning & Memory with Auto-Expiration**
- Redis-based incident storage with user isolation (SHA-256 project hashing)
- Automatic TTL expiration (default 30 days) prevents stale data
- Sub-second similarity search using Redis sorted sets
- Severity-based indexing (P0/P1/P2/P3) for quick critical incident lookup
- Graceful fallback to file-based storage if Redis unavailable

---

## System Architecture

### Architecture Pattern: Multi-Agent State Machine

OpsPilot uses a **state-based workflow** where each agent transforms the system state:

```python
State = {
    project_root: str,
    context: dict,           # Gathered from multiple sources
    hypothesis: str,         # Generated by Planner
    confidence: float,       # Updated by Verifier
    evidence: dict,          # Collected by Verifier
    suggestions: list,       # Generated by Fixer
    terminated: bool         # Workflow control flag
}
```

### Workflow States

1. **Initial State**: Empty state with only `project_root`
2. **Context Collected**: State populated with logs, env, deps, etc.
3. **Hypothesis Formed**: Planner adds hypothesis and initial confidence
4. **Evidence Gathered**: Verifier collects concrete evidence
5. **Hypothesis Verified**: Verifier updates confidence based on evidence
6. **Fixes Suggested** (if confidence ≥ 0.6): Fixer generates suggestions
7. **Terminal State**: Workflow completes

---

## Agent Design

### 1. Planner Agent (`agents/planner.py`)

**Responsibility**: Analyze project context and generate hypotheses about root causes

**Input**: Project context (logs, env vars, dependencies, structure)

**Output**:
```json
{
  "hypothesis": "Redis connection issue caused by network timeout",
  "confidence": 0.8,
  "possible_causes": ["Network latency", "Redis server down"],
  "required_checks": ["Verify Redis connectivity", "Check network logs"]
}
```

**LLM Prompt Strategy**:
- Role: Senior Site Reliability Engineer
- Task: Analyze context and form hypothesis
- Output: Strict JSON format (no explanatory text)
- Context Summarization: Limits logs to 2000 chars, deps to 20 items (token optimization)

**Key Features**:
- Context summarization to reduce LLM token usage
- Robust JSON extraction (handles LLM adding explanatory text)
- 120-second timeout with error handling

---

### 2. Verifier Agent (`agents/verifier.py`)

**Responsibility**: Validate hypotheses using concrete evidence

**Input**:
- Hypothesis from Planner
- Evidence collected from tools

**Output**:
```json
{
  "supported": true,
  "confidence": 0.8,
  "reason": "Log errors and Redis usage confirm connection issue"
}
```

**Evidence Types**:
- `log_errors`: Error counts by type (ERROR, Timeout, Exception)
- `missing_env`: Required environment variables not found
- `uses_redis`: Boolean flag for Redis dependency
- More evidence types can be added via tools

**Decision Logic**:
- Confidence ≥ 0.6 → Proceed to Fixer
- Confidence < 0.6 → Terminate workflow (not enough certainty)

---

### 3. Fixer Agent (`agents/fixer.py`)

**Responsibility**: Generate safe, actionable fix suggestions

**Input**:
- Hypothesis
- Evidence

**Output**:
```json
{
  "suggestions": [
    {
      "file": ".env",
      "diff": "--- a/.env\n+++ b/.env\n-REDIS_TIMEOUT=1\n+REDIS_TIMEOUT=5",
      "rationale": "Increase timeout to reduce transient errors"
    }
  ]
}
```

**Fix Strategy**:
1. **Domain-Specific Fixes** (hardcoded templates)
   - Redis timeout adjustment
   - Redis connection pooling
   - More domains can be added (PostgreSQL, MongoDB, etc.)

2. **LLM-Generated Fixes** (fallback)
   - If no template matches, use LLM to generate custom suggestions
   - Output as unified diff format

**Safety Guarantees**:
- All fixes shown as diffs (preview before apply)
- Rationale provided for each suggestion
- User must manually apply changes

---

### 4. Remediation Agent (`agents/remediation.py`)

**Responsibility**: Generate comprehensive 3-tier action plans

**Input**:
- Severity level (P0/P1/P2/P3)
- Error patterns
- Evidence

**Output**:
```json
{
  "immediate_actions": [
    "Restart Redis service",
    "Check Redis server logs for errors"
  ],
  "short_term_fixes": [
    "Increase Redis timeout to 5 seconds",
    "Enable connection pooling (max 20 connections)"
  ],
  "long_term_improvements": [
    "Set up Redis cluster for high availability",
    "Implement circuit breaker pattern"
  ],
  "verification_steps": [
    "Monitor error rate after changes",
    "Verify Redis response times < 100ms"
  ]
}
```

**Strategy**:
- **Immediate**: Actions to take right now (P0/P1 incidents)
- **Short-term**: Fixes to apply within hours/days
- **Long-term**: Architectural improvements for prevention
- **Verification**: How to confirm the issue is resolved

---

## Multi-Provider LLM System

### Architecture

OpsPilot uses a **router-based multi-provider system** with automatic fallback:

```python
LLMRouter
├── OllamaProvider (local, priority 1)
│   ├── Health check: ollama list
│   ├── Model: llama3
│   └── Timeout: 60s
├── OpenRouterProvider (cloud, priority 2)
│   ├── Health check: API key present
│   ├── Model: google/gemini-2.0-flash-exp:free
│   └── Timeout: 60s
├── GeminiProvider (cloud, priority 3)
│   ├── Health check: API key present
│   ├── Model: gemini-2.0-flash
│   └── Timeout: 60s
└── HuggingFaceProvider (cloud, priority 4)
    ├── Health check: API key present
    ├── Model: mistralai/Mixtral-8x7B-Instruct-v0.1
    └── Timeout: 60s
```

### Fallback Logic

```python
def call(prompt: str, timeout: int) -> str:
    errors = []

    # Try last successful provider first (sticky routing)
    if self.last_successful_provider:
        try:
            return self.last_successful_provider.call(prompt)
        except Exception as e:
            errors.append(f"{provider}: {e}")

    # Try all available providers in order
    for provider in self.providers:
        if not provider.is_available():
            continue

        try:
            result = provider.call(prompt)
            self.last_successful_provider = provider  # Remember success
            return result
        except Exception as e:
            errors.append(f"{provider}: {e}")
            continue

    # All providers failed
    raise RuntimeError(f"All LLM providers failed:\n{errors}")
```

### Provider Health Tracking

The system tracks LLM provider health metrics in Redis:

```python
# Per-provider metrics
redis.hset("llm:health:OllamaProvider", {
    "success_count": 142,
    "failure_count": 3,
    "avg_latency_ms": 234.5,
    "last_success": 1736704800
})
```

### Configuration

Users can control provider preference via environment variables:

```bash
# Prefer local over cloud (default: true)
OPSPILOT_PREFER_LOCAL=true

# LLM inference timeout (default: 60s)
OPSPILOT_LLM_TIMEOUT=60

# API keys for cloud providers (optional)
OPENROUTER_API_KEY=sk-or-v1-...
GOOGLE_API_KEY=...
HUGGINGFACE_API_KEY=hf_...
```

---

## Redis-Based Memory System

### User Isolation Strategy

**Problem**: Multiple users/projects must not see each other's incidents

**Solution**: SHA-256 project path hashing

```python
def _get_project_hash(project_root: str) -> str:
    return hashlib.sha256(project_root.encode()).hexdigest()[:16]

# User 1: /home/alice/app → hash: a1b2c3d4e5f6g7h8
# User 2: /home/bob/app   → hash: x9y8z7w6v5u4t3s2

# Complete key isolation
incident:a1b2c3d4:1234567890  # Alice's incident
incident:x9y8z7w6:1234567890  # Bob's incident
```

### Redis Schema Design

```python
# 1. Individual incidents (auto-expire after TTL)
Key:   incident:{project_hash}:{timestamp}
Value: JSON {hypothesis, confidence, severity, evidence, ...}
TTL:   2592000 seconds (30 days, configurable)

# 2. Similarity index (sorted set by confidence)
Key:    incidents:similar:{project_hash}
Score:  confidence (0.0 - 1.0)
Member: incident_key
TTL:    2592000 seconds

# 3. Severity index (set per severity level)
Key:   incidents:severity:{project_hash}:{P0/P1/P2/P3}
Value: Set of incident_keys
TTL:   2592000 seconds

# 4. LLM provider health (global, shared)
Key:   llm:health:{provider_name}
Value: Hash {success_count, failure_count, avg_latency_ms}
TTL:   3600 seconds (1 hour)
```

### Why TTL-Based Expiration?

**Problem**: PostgreSQL would accumulate fixed incidents forever

**Solution**: Redis TTL automatically expires old data

```python
# Incident stored with TTL
redis.setex(
    key=f"incident:{project_hash}:{timestamp}",
    time=OPSPILOT_REDIS_TTL_DAYS * 24 * 60 * 60,  # Default: 30 days
    value=json.dumps(incident_data)
)

# After 30 days: Redis automatically deletes the key
# No cleanup jobs needed, no stale data accumulation
```

### Performance Characteristics

```python
# Similarity search: O(log N) with sorted sets
similar = redis.zrevrangebyscore(
    f"incidents:similar:{project_hash}",
    max=1.0,
    min=0.6,
    start=0,
    num=5
)
# Returns top 5 similar incidents in <10ms

# Severity filter: O(1) with set membership
p0_incidents = redis.smembers(f"incidents:severity:{project_hash}:P0")
# Returns all P0 incidents in <5ms
```

### Graceful Degradation

```python
try:
    redis_memory = RedisMemory()
    if not redis_memory.health_check():
        raise RuntimeError("Redis unavailable")
except Exception:
    # Fallback to file-based memory
    print("[INFO] Using file-based memory (Redis unavailable)")
    from opspilot.memory import load_memory, save_memory
    # System continues working with file-based storage
```

---

## Data Flow

### Complete Execution Flow

```
User runs: opspilot analyze
          │
          ▼
┌─────────────────────────┐
│  1. Initialize State    │
│     (project_root)      │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  2. Collect Context     │
│     - Scan logs         │
│     - Read .env         │
│     - Parse deps        │
│     - Check Docker      │
│     - Map structure     │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  3. Planner Agent       │
│     - Summarize context │
│     - Call LLM          │
│     - Extract JSON      │
│     - Form hypothesis   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  4. Collect Evidence    │
│     - Analyze logs      │
│     - Check env vars    │
│     - Detect deps       │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  5. Verifier Agent      │
│     - Match evidence    │
│     - Update confidence │
│     - Decide next step  │
└──────────┬──────────────┘
           │
           ▼
      Confidence ≥ 0.6?
           │
    ┌──────┴──────┐
    │ YES         │ NO
    ▼             ▼
┌─────────────┐  ┌─────────────┐
│ 6. Fixer    │  │ 7. Terminate│
│    Agent    │  │    (Low     │
│    - Gen    │  │  Confidence)│
│      fixes  │  └─────────────┘
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│  8. Save to Memory      │
│     (~/.opspilot_mem)   │
└──────────┬──────────────┘
           │
           ▼
    Display Results
```

---

## State Management

### AgentState Dataclass

```python
@dataclass
class AgentState:
    project_root: str
    context: Dict[str, Any] = field(default_factory=dict)
    hypothesis: Optional[str] = None
    confidence: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[Dict[str, Any]] = field(default_factory=list)
    checks_remaining: List[str] = field(default_factory=list)
    iteration: int = 0
    terminated: bool = False
```

### State Transitions

Each agent is implemented as a **pure function** that takes state and returns updated state:

```python
def planner_node(state: AgentState) -> AgentState:
    result = plan(state.context)
    state.hypothesis = result.get("hypothesis")
    state.confidence = result.get("confidence", 0.0)
    state.iteration += 1
    return state

def verifier_node(state: AgentState) -> AgentState:
    state.evidence = collect_evidence(state.context)
    verdict = verify(state.hypothesis, state.evidence)
    state.confidence = verdict.get("confidence", state.confidence)
    return state

def fixer_node(state: AgentState) -> AgentState:
    if state.confidence >= CONFIDENCE_THRESHOLD:
        fixes = suggest(state.hypothesis, state.evidence)
        state.suggestions = fixes.get("suggestions", [])
    return state
```

### Workflow Termination

The workflow terminates when:
1. Confidence ≥ 0.6 and fixes are generated, OR
2. Confidence < 0.6 (insufficient evidence), OR
3. Maximum iterations reached (safety limit)

---

## LLM Integration

### Multi-Provider Strategy

OpsPilot uses a **router-based multi-provider system** with automatic fallback (see [Multi-Provider LLM System](#multi-provider-llm-system) section above for details).

**Why Multi-Provider?**
- ✅ **High Availability**: Automatic failover if one provider is down
- ✅ **Cost Optimization**: Prefer free local inference (Ollama)
- ✅ **Flexibility**: All providers use FREE tiers (no API costs)
- ✅ **Privacy Options**: Can run 100% offline with Ollama only
- ✅ **Vendor Independence**: Not locked into single provider

### Prompt Engineering Techniques

#### 1. Structured Output Prompting
```python
SYSTEM_PROMPT = """
You are a senior site reliability engineer.
Your task is to analyze project context and form a hypothesis.

CRITICAL: Your response must be ONLY valid JSON with this exact format:
{
  "hypothesis": "...",
  "confidence": 0.0,
  "possible_causes": ["..."],
  "required_checks": ["..."]
}

Do not include any text before the opening { or after the closing }.
"""
```

#### 2. Context Summarization (Token Optimization)
```python
summarized_context = {
    "logs": context.get("logs", "")[:2000],           # Limit to 2000 chars
    "env": list(context.get("env", {}).keys()),      # Only var names
    "dependencies": context.get("dependencies", [])[:20],  # Top 20
    "structure": str(context.get("structure", ""))[:1000]  # Limit
}
```

#### 3. Robust JSON Extraction
```python
# LLMs often add explanatory text before/after JSON
# Extract JSON between first { and last }
start_idx = raw_output.find('{')
end_idx = raw_output.rfind('}')
if start_idx != -1 and end_idx != -1:
    json_str = raw_output[start_idx:end_idx + 1]
    result = json.loads(json_str)
```

#### 4. Error Handling & Timeouts
- 120-second timeout per LLM call (prevents hanging)
- Fallback responses on JSON parsing errors
- Informative error messages for debugging

---

## Design Decisions

### Why Multi-Agent Instead of Single LLM Call?

**Pros**:
- ✅ **Separation of concerns**: Each agent has a focused task
- ✅ **Easier to debug**: Can inspect state between agents
- ✅ **Modular**: Can replace/upgrade individual agents
- ✅ **Testable**: Each agent can be tested independently
- ✅ **Iterative refinement**: Can add feedback loops later

**Cons**:
- ❌ More LLM calls (higher latency)
- ❌ More complex state management

**Decision**: Multi-agent for maintainability and extensibility

---

### Why Confidence Threshold = 0.6?

**Rationale**:
- Too low (0.4): Generates fixes with weak evidence (risky)
- Too high (0.8): Rarely generates fixes (not helpful)
- 0.6: Balanced - requires moderate evidence strength

**Tunable**: Can be made configurable in future versions

---

### Why Dry-Run Only (No Auto-Apply)?

**Safety-Critical Decision**:
- Automatically applying code changes is dangerous
- User should review and approve all changes
- Builds trust in the system
- Easier to debug if something goes wrong

**Trade-off**: Less automated, but much safer

---

### Why Multi-Provider LLM System?

**Pros**:
- ✅ High availability (automatic failover)
- ✅ Zero cost (all providers use FREE tiers)
- ✅ Privacy option (can use Ollama only)
- ✅ Vendor independence (not locked in)
- ✅ No single point of failure

**Cons**:
- ❌ More complex implementation
- ❌ Requires API key management

**Decision**: Multi-provider for reliability while maintaining free/open-source principles

---

### Why Redis Over PostgreSQL for Memory?

**Redis Pros**:
- ✅ Auto-expiring data (TTL) - no stale incidents
- ✅ Sub-second lookups (critical for incident response)
- ✅ Simple key-value schema (no migrations)
- ✅ In-memory speed (perfect for real-time)
- ✅ Built-in sorted sets for similarity search

**PostgreSQL Cons**:
- ❌ Would accumulate fixed incidents forever
- ❌ Requires cleanup jobs for old data
- ❌ Slower for simple lookups
- ❌ Schema migrations needed

**Decision**: Redis for hot data (30 days), can add PostgreSQL later for long-term analytics if needed

---

## Future Enhancements

### Completed Features ✅

- ✅ **Multi-Provider LLM Support**: Ollama, OpenRouter, Gemini, HuggingFace with automatic fallback
- ✅ **Redis-Based Memory**: User-isolated storage with auto-expiring TTL
- ✅ **Severity Classification**: P0/P1/P2/P3 incident prioritization
- ✅ **Production Log Fetching**: S3, Kubernetes, CloudWatch integration
- ✅ **Deployment Correlation**: Git-based deployment history analysis
- ✅ **Comprehensive Testing**: 45+ unit tests with pytest

### Planned Improvements

#### 1. **Plugin System**
```python
# Allow users to register custom agents
opspilot.register_agent("my_custom_agent", MyAgentClass)

# Allow custom evidence collectors
opspilot.register_tool("my_evidence_tool", my_tool_function)
```

#### 2. **Web API Layer**
```python
# FastAPI endpoint
POST /api/analyze
{
  "project_path": "/path/to/project",
  "options": {
    "confidence_threshold": 0.7
  }
}
```

#### 3. **Feedback Loop (Self-Improvement)**
```python
# Agent can re-run if confidence is low
while state.confidence < 0.6 and state.iteration < max_iterations:
    state = collect_more_evidence(state)
    state = verifier_node(state)
```

#### 4. **Real-Time Metrics Dashboard**
- Track success rate of hypotheses
- Measure confidence accuracy
- Monitor LLM response times
- Visualize incident trends over time
- Provider health monitoring UI

#### 5. **Incident Alert Integration**
- Slack notifications for P0/P1 incidents
- PagerDuty integration
- Custom webhook support
- Email alerts with incident summary

#### 6. **Advanced Evidence Collection**
- API endpoint testing
- Database query analysis
- Network connectivity checks
- Resource usage metrics

#### 7. **Domain-Specific Agents**
- PostgreSQL expert agent
- MongoDB expert agent
- Kubernetes expert agent
- AWS/Cloud infrastructure agent

---

## Summary

OpsPilot's architecture is designed for:
- ✅ **Safety**: Dry-run only, evidence-based decisions
- ✅ **High Availability**: Multi-provider LLM with automatic failover
- ✅ **Modularity**: Easy to extend with new agents/tools
- ✅ **Transparency**: Clear state transitions, confidence scores, severity classification
- ✅ **Privacy-Focused**: Prefers local LLM with optional cloud fallback
- ✅ **Production-Ready**: Redis memory with user isolation, auto-expiring TTL
- ✅ **Scalability**: Sub-second incident lookups, severity indexing
- ✅ **Reliability**: Robust error handling, timeouts, graceful degradation
- ✅ **Vendor Independence**: 100% free/open-source providers, no lock-in

The multi-agent pattern combined with multi-provider LLM routing and Redis-based memory provides a robust, production-ready foundation for intelligent DevOps automation.

---

**For more details, see:**
- [README.md](README.md) - User guide and quick start
- [Contributing Guidelines](CONTRIBUTING.md) *(coming soon)*
- [API Documentation](docs/api.md) *(coming soon)*
