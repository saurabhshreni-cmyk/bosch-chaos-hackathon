from pathlib import Path
from platform_agents.schemas import digest
from platform_agents.docker_adapter import SafetyError, validate_probe


class SafetyValidator:
    def __init__(self, analysis_agent, policy, store, control_root):
        self.analysis_agent, self.policy, self.store = analysis_agent, policy, store
        self.control_root = Path(control_root)

    def stopped(self):
        return (self.control_root / "STOP").exists() or (self.analysis_agent.root / "chaos-scripts" / "STOP").exists()

    def validate(self, experiment, adapter, require_approval=False):
        p = experiment.proposal
        policy = self.policy
        if not policy.enabled:
            raise SafetyError("Fault execution is disabled by local policy")
        if not policy.watchdog_verified:
            raise SafetyError("Disposable watchdog verification must be recorded before enabling execution")
        if self.stopped() or experiment.abort_requested:
            raise SafetyError("Independent kill switch is active")
        if not p.supported or p.policy_hash != digest(policy.model_dump()) or experiment.proposal_hash != digest(p.model_dump()):
            raise SafetyError("Unsupported or changed proposal/policy")
        if not set(p.targets) <= set(policy.allowed_services) or len(p.targets) > policy.max_targets or p.duration_seconds > policy.max_duration_seconds:
            raise SafetyError("Target allowlist, simultaneous-failure or duration restriction violated")
        heartbeat = self.store.control("worker_heartbeat")
        if heartbeat is None or self.store.clock() - heartbeat > 10:
            raise SafetyError("Independent execution worker is unavailable")
        # Reinspect real source configuration, rather than trusting a cached dashboard snapshot.
        data = self.analysis_agent.analyze(False, False)
        if data["configuration_hash"] != p.source_configuration_hash:
            raise SafetyError("Application configuration changed; create and approve a new proposal")
        if not any(r["finding_id"] == p.source_finding_id for r in data["recommendations"]):
            raise SafetyError("Source recommendation no longer exists")
        required = set(p.expected_impact)
        for component in required:
            for purpose in ("readiness", "functionality", "dependency"):
                probes = [probe for probe in policy.probes if probe.component == component and probe.purpose == purpose]
                if not probes:
                    raise SafetyError(f"Missing {purpose} probe for affected component {component}")
                for probe in probes:
                    validate_probe(probe)
        environment = adapter.inspect(p.targets, required)
        baseline = adapter.probe(required)
        if not baseline or not all(row["ok"] for row in baseline):
            raise SafetyError("Functional/dependency baseline is unavailable or unhealthy")
        if require_approval:
            a = experiment.approval
            if not a or a["expires_at"] <= self.store.clock() or a["proposal_hash"] != experiment.proposal_hash:
                raise SafetyError("Approval is missing, changed or expired")
            if a["environment_fingerprint"] != environment["fingerprint"]:
                raise SafetyError("Environment changed after approval")
        return environment, baseline
