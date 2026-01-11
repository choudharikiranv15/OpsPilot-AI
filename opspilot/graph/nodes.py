from opspilot.state import AgentState
from opspilot.context import collect_context
from opspilot.agents.planner import plan
from opspilot.agents.verifier import verify
from opspilot.agents.fixer import suggest
from opspilot.tools import collect_evidence

CONFIDENCE_THRESHOLD = 0.6


def collect_context_node(state: AgentState) -> AgentState:
    state.context = collect_context(state.project_root)
    return state


def planner_node(state: AgentState) -> AgentState:
    if state.hypothesis:
        return state  # already planned this iteration

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
