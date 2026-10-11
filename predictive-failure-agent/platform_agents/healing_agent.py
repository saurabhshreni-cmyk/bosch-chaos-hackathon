import time


class SelfHealingAgent:
    """Bounded restoration of original state, with evidence separated from hypotheses."""
    def __init__(self, store, policy):
        self.store, self.policy = store, policy

    def diagnose(self, experiment, adapter):
        states = adapter.states(experiment.execution["original_ids"])
        stopped = [value for value, row in states.items() if not row["running"]]
        return {"incident_id": experiment.id, "experiment_id": experiment.id, "observed_at": self.store.clock(), "observed_states": states, "affected_components": experiment.proposal.expected_impact, "injected_targets": experiment.proposal.targets, "hypothesis": "The approved container stop may explain dependent symptoms; unrelated faults remain possible.", "evidence_status": "Observed container state; application symptoms require probe evidence", "stopped_container_ids": stopped, "playbook": "start_original_container_ids", "unexpected_incidents": "Read-only diagnosis only; spontaneous remediation is not preauthorized"}

    def recover(self, experiment, adapter):
        adapter.abort(experiment.id)  # Signals the independent watchdog before Docker calls.
        actions = []
        for container_id in experiment.execution["original_ids"]:
            try:
                adapter.start(container_id)
                actions.append({"container_id": container_id, "action": "start", "request_accepted": True})
            except Exception:
                # Never emit raw Docker exceptions, which may contain configuration values.
                actions.append({"container_id": container_id, "action": "start", "request_accepted": False, "error": "Docker restoration request failed; watchdog retained"})
        self.store.event(experiment.id, "RECOVERY_ACTIONS", {"actions": actions})
        return actions

    def verify(self, experiment, adapter):
        states = adapter.states(experiment.execution["original_ids"])
        observations = adapter.probe(set(experiment.proposal.expected_impact))
        layers = {"infrastructure": all(row["running"] for row in states.values()), "readiness": False, "dependencies": False, "functionality": False, "stability": False}
        for purpose, layer in (("readiness", "readiness"), ("dependency", "dependencies"), ("functionality", "functionality")):
            relevant = [row for row in observations if row["purpose"] == purpose]
            layers[layer] = all(any(r["component"] == component and r["ok"] for r in relevant) for component in experiment.proposal.expected_impact) and all(r["ok"] for r in relevant)
        # Docker health is additional evidence, not a substitute for functional probes.
        layers["readiness"] = layers["readiness"] and all(row["health"] != "unhealthy" for row in states.values())
        return {"timestamp": self.store.clock(), "layers": layers, "observations": observations, "states": states, "message_delivery_verified": False, "data_integrity_verified": False}
