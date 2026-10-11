import uuid
from platform_agents.schemas import Proposal, Experiment, SUPPORTED, UNSUPPORTED_REASONS, digest
from platform_agents.docker_adapter import SafetyError


class ChaosInjectionAgent:
    """Plans from actual recommendations; no LLM-generated execution instructions."""
    def __init__(self, analysis_agent, policy, store):
        self.analysis_agent, self.policy, self.store = analysis_agent, policy, store

    def recommendations(self):
        current = self.analysis_agent.latest or self.analysis_agent.analyze()
        return current["recommendations"]

    def plan(self, request):
        data = self.analysis_agent.latest or self.analysis_agent.analyze()
        source = next((r for r in data["recommendations"] if r["finding_id"] == request.source_finding_id), None)
        if not source:
            raise SafetyError("Source finding is not a current Analysis Agent recommendation")
        targets = request.targets
        available = {s["name"] for s in data["services"]}
        if len(set(targets)) != len(targets) or not set(targets) <= available:
            raise SafetyError("Targets must be distinct discovered services")
        if source["component"] not in targets:
            raise SafetyError("The recommended component must be an approved target")
        if len(targets) > 1 and request.fault_type != "multi_container_stop":
            raise SafetyError("Multiple targets require an explicit multi-container proposal")
        if len(targets) == 1 and request.fault_type == "multi_container_stop":
            raise SafetyError("A multi-container proposal must identify two targets")
        if request.fault_type == "rabbitmq_outage" and targets != ["rabbitmq"]:
            raise SafetyError("RabbitMQ adapter requires the discovered rabbitmq service")
        # Database targets require dedicated disposable-data guarantees, regardless of alias.
        database_targets = {s["name"] for s in data["services"] if any(word in (s["name"] + " " + s.get("role", "")).lower() for word in ("sqlserver", "database", "postgres", "mysql", "mongo"))}
        database_targets |= {edge["target"] for edge in data["dependencies"] if edge["kind"] == "database"}
        reason = UNSUPPORTED_REASONS.get(request.fault_type)
        if set(targets) & database_targets:
            reason = UNSUPPORTED_REASONS["database_outage"]
        supported = request.fault_type in SUPPORTED and reason is None
        # Consumer -> dependency: traverse reverse edges to discover affected consumers.
        affected = set(targets)
        while True:
            extended = affected | {d["source"] for d in data["dependencies"] if d["target"] in affected and d["kind"] not in {"startup", "logging"}}
            if extended == affected:
                break
            affected = extended
        proposal = Proposal(**request.model_dump(), experiment_id=str(uuid.uuid4()), title=f"{request.fault_type}: {', '.join(targets)}", hypothesis=source["hypothesis"], expected_impact=sorted(affected), metrics_to_monitor=source["metrics"], source_configuration_hash=data["configuration_hash"], source_prediction=source, policy_hash=digest(self.policy.model_dump()), supported=supported, unsupported_reason=reason)
        experiment = Experiment(id=proposal.experiment_id, state="AWAIT_USER_APPROVAL" if supported else "UNSUPPORTED", proposal=proposal, proposal_hash=digest(proposal.model_dump()), created_at=self.store.clock())
        self.store.create(experiment)
        from platform_agents.reasoning import explain
        self.store.event(experiment.id, "AI_CHAOS_HYPOTHESIS", explain(self.analysis_agent.storage, experiment, "chaos"))
        return experiment
