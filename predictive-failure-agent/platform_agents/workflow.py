from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class WorkflowState(TypedDict):
    experiment_id: str
    phase: str


def plan(platform, request):
    """Analysis and chaos nodes share the existing analysis output, not copies."""
    graph = StateGraph(WorkflowState)
    def analyze(state):
        platform.agent.analyze(False, False)
        return {"phase": "RECOMMEND"}
    def propose(state):
        experiment = platform.chaos.plan(request)
        return {"experiment_id": experiment.id, "phase": experiment.state}
    def approval_gate(state):
        # This boundary returns immediately; only a separate authenticated request
        # can add an approval to the persisted proposal.
        return state
    graph.add_node("Analysis_Agent", analyze)
    graph.add_node("Chaos_Injection_Agent", propose)
    graph.add_node("Approval_Gate", approval_gate)
    graph.add_edge(START, "Analysis_Agent")
    graph.add_edge("Analysis_Agent", "Chaos_Injection_Agent")
    graph.add_edge("Chaos_Injection_Agent", "Approval_Gate")
    graph.add_edge("Approval_Gate", END)
    result = graph.compile().invoke({"experiment_id": "", "phase": "ANALYZE"})
    return platform.store.get(result["experiment_id"])


def dispatch(platform, experiment):
    """One database-backed transition per invocation; approval wait holds no thread.

    SQLite is the durable source of truth. Checkpoint replay is deliberately not used
    for non-idempotent Docker stops. A restarted INJECTING node always rolls back.
    """
    names = {"QUEUED": "Safety_Approval_Fault_Executor", "INJECTING": "Recovery_Watchdog_Interface", "OBSERVE": "Observation_Controller", "RECOVERING": "Self_Healing_Agent", "FAILED_RECOVERY": "Recovery_Watchdog_Interface", "VERIFY": "Recovery_Verifier_Report_Feedback"}
    node = names[experiment.state]
    graph = StateGraph(WorkflowState)
    def step(state):
        # Reload authoritative state, never act from a stale graph checkpoint.
        current = platform.store.get(state["experiment_id"])
        if current.state == experiment.state:
            platform.step(current)
        return {"phase": platform.store.get(current.id).state}
    graph.add_node(node, step)
    graph.add_edge(START, node)
    graph.add_edge(node, END)
    return graph.compile().invoke({"experiment_id": experiment.id, "phase": experiment.state})
