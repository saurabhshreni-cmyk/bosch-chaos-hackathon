"""Optional narrative only. No log bodies, environment values or operation authority."""
import os
from llm.groq_client import GroqReasoner


def explain(storage, experiment, agent, observations=None):
    if os.getenv("PFIA_ENABLE_GROQ", "false").lower() != "true":
        return {"status": "Groq disabled; deterministic workflow retained", "narrative": None}
    source = experiment.proposal.source_prediction
    component = source["component"]
    evidence = {"components": [component], "findings": [{"id": source["finding_id"], "component": component, "hypothesis": source["hypothesis"], "status": "evidence-supported hypothesis"}], "agent_role": agent, "fault_type": experiment.proposal.fault_type, "observations": observations or {}, "instruction": "Explain hypotheses only. Recovery decisions and scores are deterministic. Never claim data integrity or message delivery."}
    try:
        reasoner = GroqReasoner(storage)
        reasoner.max_calls = min(reasoner.max_calls, 3)  # Listing plus at most two bounded attempts.
        return reasoner.explain(evidence, complex_analysis=len(experiment.proposal.targets) > 1, agent=agent, experiment_id=experiment.id)
    except Exception:
        return {"status": "AI explanation unavailable; deterministic workflow retained", "narrative": None}
