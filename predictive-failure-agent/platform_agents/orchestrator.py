"""Database transitions are authoritative; LangGraph dispatches one resumable step.

No graph replay may inject a fault. INJECTING resumes through rollback, never injection.
"""
import json
import os
import time
from pathlib import Path
from platform_agents.schemas import Policy, TERMINAL, digest
from platform_agents.state_store import StateStore, Conflict
from platform_agents.chaos_agent import ChaosInjectionAgent
from platform_agents.healing_agent import SelfHealingAgent
from platform_agents.safety import SafetyValidator
from platform_agents.docker_adapter import DockerAdapter, SafetyError


class Platform:
    def __init__(self, agent, policy=None, adapter_factory=None, clock=time.time):
        self.agent = agent
        self.policy_path = os.getenv("PFIA_POLICY_FILE")
        self.policy = policy or (Policy.model_validate_json(Path(self.policy_path).read_text()) if self.policy_path else Policy())
        self.store = StateStore(agent.storage, clock)
        self.control_root = agent.storage.path.parent / "chaos-control"
        self.control_root.mkdir(parents=True, exist_ok=True)
        self.adapter_factory = adapter_factory or (lambda: DockerAdapter(self.policy, self.control_root))
        self.safety = SafetyValidator(agent, self.policy, self.store, self.control_root)
        self.chaos = ChaosInjectionAgent(agent, self.policy, self.store)
        self.healing = SelfHealingAgent(self.store, self.policy)

    def check_policy_file(self):
        if self.policy_path and Policy.model_validate_json(Path(self.policy_path).read_text()) != self.policy:
            raise SafetyError("Policy file changed; restart the backend and worker and obtain new approval")

    def approve(self, experiment_id, body, operator):
        experiment = self.store.get(experiment_id)
        if body.proposal_hash != experiment.proposal_hash:
            raise SafetyError("Approval does not match the immutable proposal")
        self.check_policy_file()
        adapter = self.adapter_factory()
        try:
            environment, baseline = self.safety.validate(experiment, adapter)
        finally:
            adapter.close()
        def update(current):
            current.approval = {"operator": operator, "approved_at": self.store.clock(), "expires_at": self.store.clock() + self.policy.approval_ttl_seconds, "proposal_hash": current.proposal_hash, "environment_fingerprint": environment["fingerprint"], "baseline": baseline}
            current.state = "APPROVED"
        return self.store.change(experiment_id, {"AWAIT_USER_APPROVAL"}, update)

    def execute(self, experiment_id):
        experiment = self.store.get(experiment_id)
        self.check_policy_file()
        adapter = self.adapter_factory()
        try:
            self.safety.validate(experiment, adapter, True)
        except SafetyError:
            if experiment.state == "APPROVED":
                self.store.change(experiment_id, {"APPROVED"}, lambda e: setattr(e, "state", "INVALIDATED"))
            raise
        finally:
            adapter.close()
        return self.store.change(experiment_id, {"APPROVED"}, lambda e: setattr(e, "state", "QUEUED"), exclusive=True)

    def reject(self, experiment_id):
        return self.store.change(experiment_id, {"AWAIT_USER_APPROVAL", "APPROVED"}, lambda e: setattr(e, "state", "REJECTED"))

    def abort(self, experiment_id):
        experiment = self.store.get(experiment_id)
        if experiment.state in TERMINAL:
            return experiment
        # Filesystem signal comes first, independent of Docker/LLM/SQLite availability.
        folder = self.control_root / experiment.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ABORT").touch()
        def update(current):
            current.abort_requested = True
            if current.state in {"AWAIT_USER_APPROVAL", "APPROVED", "QUEUED"}:
                current.state = "CANCELLED"
        return self.store.change(experiment.id, {experiment.state}, update)

    def heartbeat(self):
        self.store.control("worker_heartbeat", self.store.clock())
        heartbeat = self.control_root / "heartbeat.tmp"
        heartbeat.write_text(str(int(self.store.clock())))
        heartbeat.replace(self.control_root / "heartbeat")

    def tick(self):
        self.heartbeat()
        for experiment in self.store.list():
            if experiment.state == "APPROVED" and experiment.approval["expires_at"] <= self.store.clock():
                self.store.change(experiment.id, {"APPROVED"}, lambda e: setattr(e, "state", "EXPIRED"))
            elif experiment.state not in TERMINAL | {"APPROVED", "AWAIT_USER_APPROVAL"}:
                from platform_agents.workflow import dispatch
                dispatch(self, experiment)

    def step(self, experiment):
        if experiment.state == "FAILED_RECOVERY" and experiment.execution.get("adapter_failures", 0) >= 3:
            return
        adapter = None
        try:
            adapter = self.adapter_factory()
            if experiment.state == "QUEUED":
                self._inject(experiment, adapter)
            elif experiment.state in {"INJECTING", "RECOVERING", "FAILED_RECOVERY"}:
                # A crash at any point in injection cannot cause replay of a stop request.
                self._recover(experiment, adapter)
            elif experiment.state == "OBSERVE":
                self._observe(experiment, adapter)
            elif experiment.state == "VERIFY":
                self._verify(experiment, adapter)
        except Conflict:
            pass
        except Exception:
            current = self.store.get(experiment.id)
            if current.execution.get("original_ids"):
                folder = self.control_root / current.id
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "ABORT").touch()
                def failed(e):
                    e.state = "FAILED_RECOVERY"
                    if adapter is None:
                        e.execution["adapter_failures"] = e.execution.get("adapter_failures", 0) + 1
                self.store.change(current.id, {current.state}, failed)
                self.store.event(current.id, "ERROR", {"message": "Workflow/Docker operation failed; rollback lease and watchdog retained", "watchdog_id": current.execution.get("watchdog_id")})
            elif current.state == "QUEUED":
                self.store.change(current.id, {"QUEUED"}, lambda e: setattr(e, "state", "INVALIDATED"))
                self.store.event(current.id, "ERROR", {"message": "Preflight or approval validation failed; no fault injected"})
        finally:
            if adapter is not None:
                adapter.close()

    def _inject(self, experiment, adapter):
        self.check_policy_file()
        environment, baseline = self.safety.validate(experiment, adapter, True)
        now = self.store.clock()
        ids = [environment["containers"][target]["id"] for target in experiment.proposal.targets]
        def lease(current):
            current.state = "INJECTING"
            current.execution = {"original_ids": ids, "original_environment": environment, "baseline": baseline, "started_at": now, "deadline": now + current.proposal.duration_seconds, "injected_ids": [], "watchdog_id": None, "stop_requests_settled": False}
        current = self.store.change(experiment.id, {"QUEUED"}, lease, exclusive=True)
        watchdog_id = adapter.arm(current.id, ids, current.execution["deadline"])
        self.store.change(current.id, {"INJECTING"}, lambda e: e.execution.update(watchdog_id=watchdog_id))
        adapter.start_watchdog(watchdog_id)
        ready = False
        for _ in range(5):
            if adapter.watchdog_ready(current.id, watchdog_id):
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            raise SafetyError("Independent watchdog did not acknowledge its lease")
        # Validate again after arming; a watchdog may not substitute for approval.
        self.safety.validate(self.store.get(current.id), adapter, True)
        for container_id in ids:
            latest = self.store.get(current.id)
            if latest.abort_requested or self.safety.stopped() or self.store.clock() >= latest.execution["deadline"] or not adapter.watchdog_ready(current.id, watchdog_id):
                raise SafetyError("Experiment aborted or watchdog/deadline unavailable before injection")
            self.store.event(current.id, "INJECTION_REQUEST", {"container_id": container_id, "action": "stop", "timestamp": self.store.clock()})
            self.store.change(current.id, {"INJECTING"}, lambda e: e.execution.setdefault("first_stop_requested_at", self.store.clock()))
            adapter.stop(container_id)
            if adapter.states([container_id])[container_id]["running"]:
                raise SafetyError("Docker accepted the stop request but the fault was not observed")
            self.store.event(current.id, "INJECTION_ACCEPTED", {"container_id": container_id})
            self.store.change(current.id, {"INJECTING"}, lambda e: e.execution["injected_ids"].append(container_id))
        def observing(e):
            e.execution.update(stop_requests_settled=True, injection_finished_at=self.store.clock())
            e.state = "OBSERVE"
        self.store.change(current.id, {"INJECTING"}, observing)

    def _observe(self, experiment, adapter):
        incident = self.healing.diagnose(experiment, adapter)
        observations = adapter.probe(set(experiment.proposal.expected_impact))
        self.store.event(experiment.id, "OBSERVATION", {"incident": incident, "probes": observations})
        def update(current):
            current.execution["incident"] = incident
            current.execution["last_observed_probes"] = observations
            current.execution["observed_failed_components"] = sorted(set(current.execution.get("observed_failed_components", [])) | {row["component"] for row in observations if not row["ok"]})
            if any(not row["ok"] for row in observations) and "detected_at" not in current.execution:
                current.execution["detected_at"] = self.store.clock()
            threshold = sum(not row["ok"] for row in observations) > self.policy.max_failed_probes
            if current.abort_requested or self.safety.stopped() or threshold or self.store.clock() >= current.execution["deadline"]:
                current.state = "RECOVERING"
                if threshold:
                    current.execution["abort_reason"] = "Configured failed-probe threshold exceeded"
        self.store.change(experiment.id, {"OBSERVE"}, update)

    def _recover(self, experiment, adapter):
        if experiment.execution.get("recovery_attempts", 0) >= 3:
            return  # Escalated lease stays visible; independent watchdog continues restoration.
        def attempted(e):
            e.execution["recovery_attempts"] = e.execution.get("recovery_attempts", 0) + 1
            e.execution.setdefault("recovery_started_at", self.store.clock())
        self.store.change(experiment.id, {experiment.state}, attempted)
        self.healing.recover(experiment, adapter)
        def update(current):
            current.state = "VERIFY"
            current.execution.setdefault("recovery_started_at", self.store.clock())
            current.execution.setdefault("verification_deadline", self.store.clock() + 60)
            current.execution.setdefault("verification_rounds", [])
        self.store.change(experiment.id, {experiment.state}, update)

    def _verify(self, experiment, adapter):
        result = self.healing.verify(experiment, adapter)
        now = self.store.clock()
        passed = all(value for key, value in result["layers"].items() if key != "stability")
        start = experiment.execution.get("stable_since") if passed else None
        start = (start if start is not None else now) if passed else None
        stable = start is not None and now - start >= self.policy.stability_seconds
        result["layers"]["stability"] = stable
        self.store.event(experiment.id, "VERIFICATION", result)
        def record(current):
            current.execution["stable_since"] = start
            current.execution["verification_rounds"] = (current.execution["verification_rounds"] + [result])[-35:]
        current = self.store.change(experiment.id, {"VERIFY"}, record)
        # Ambiguous/failed Docker stop requests retain the lease for operator investigation.
        settled = current.execution.get("stop_requests_settled", False)
        grace_elapsed = now >= current.execution.get("injection_finished_at", now) + 10
        if stable and settled and grace_elapsed:
            adapter.abort(current.id)
            if current.execution.get("watchdog_id"):
                adapter.release(current.id, current.execution["watchdog_id"])
            self._report(current, "COMPLETED", result)
        elif now >= current.execution["verification_deadline"]:
            # Retain watchdog and the global lease for uncertain rollback, never report success.
            self._report(current, "FAILED_RECOVERY", result)

    def _report(self, experiment, state, verification):
        now = self.store.clock()
        report = {"experiment_id": experiment.id, "source_prediction": experiment.proposal.source_prediction, "approved_proposal": experiment.proposal.model_dump(), "actual_injected_container_ids": experiment.execution.get("injected_ids", []), "baseline": experiment.execution.get("baseline"), "incident": experiment.execution.get("incident"), "verification": verification, "outcome": state, "detection_seconds": experiment.execution["detected_at"] - experiment.execution["first_stop_requested_at"] if "detected_at" in experiment.execution and "first_stop_requested_at" in experiment.execution else None, "detection_time_basis": "First failed configured probe minus first stop request; polling resolution is not exact failure onset", "recovery_seconds": now - experiment.execution["recovery_started_at"], "prediction_comparison": "Compare recorded probe observations with the hypothesis; no causal certainty or message-delivery guarantee is inferred.", "weakness_fixed": False, "watchdog_id": experiment.execution.get("watchdog_id"), "limitations": ["A restart does not repair application resilience controls or committed-row/unpublished-event inconsistencies.", "No claim of message losslessness or business-data integrity."]}
        observed = experiment.execution.get("observed_failed_components", [])
        report["prediction_comparison"] = {"predicted_possible_impact": experiment.proposal.expected_impact, "observed_probe_failure_components": observed, "predicted_components_without_observed_failure": sorted(set(experiment.proposal.expected_impact) - set(observed)), "interpretation": "Absence of an observed failure is not proof of resilience; probes and sampling are incomplete."}
        report["observed_symptoms"] = experiment.execution.get("last_observed_probes", [])
        report["recovery_actions"] = [event["data"] for event in self.store.events(experiment.id) if event["kind"] == "RECOVERY_ACTIONS"]
        report["recommendations"] = [experiment.proposal.source_prediction.get("mitigation", "Improve and verify dependency resilience controls"), "Verify consumer reconnection and business-data integrity separately without assuming a restart repairs them"]
        def update(current):
            current.report = report
            current.state = state
        self.store.change(experiment.id, {"VERIFY"}, update)
        self.store.event(experiment.id, "REPORT", report)
        from platform_agents.reasoning import explain
        self.store.event(experiment.id, "AI_HEALING_HYPOTHESIS", explain(self.agent.storage, experiment, "healing", {"verification_layers": verification["layers"], "outcome": state}))
        # Verified observations supplement analysis; successful restoration does not lower static risk.
        verified_degradation = state == "FAILED_RECOVERY" and verification["layers"]["infrastructure"] and not verification["layers"]["functionality"] and experiment.execution.get("stop_requests_settled", False) and len(experiment.execution.get("injected_ids", [])) == len(experiment.execution["original_ids"])
        self.agent.storage.save("experiment_feedback", {"experiment_id": experiment.id, "configuration_hash": experiment.proposal.source_configuration_hash, "components": experiment.proposal.expected_impact, "outcome": state, "functional_recovery_verified": state == "COMPLETED", "verified_probe_degradation": verified_degradation, "weakness_fixed": False, "risk_score_adjustment": 5 if verified_degradation else 0, "timestamp": now})
