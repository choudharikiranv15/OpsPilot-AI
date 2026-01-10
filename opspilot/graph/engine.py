from opspilot.state import AgentState
from opspilot.graph.nodes import (
    collect_context_node,
    planner_node,
    verifier_node,
    fixer_node,
)

CONFIDENCE_THRESHOLD = 0.6


def run_agent(state: AgentState) -> AgentState:
    # START → CONTEXT
    state = collect_context_node(state)

    while not state.terminated:
        # PLAN
        state = planner_node(state)

        # VERIFY
        state = verifier_node(state)

        # DECISION
        if state.confidence >= CONFIDENCE_THRESHOLD:
            state = fixer_node(state)
            state.terminated = True

        elif state.iteration >= state.max_iterations:
            state.terminated = True

        # else → loop back to PLAN

    return state
