"""Synthetic unit/mocked-infrastructure tests. Never call Docker or live providers."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from agent.predictive_agent import PredictiveAgent
from backend.main import create_app
from platform_agents.schemas import Policy, Probe, PlanRequest, ApprovalRequest, digest
from platform_agents.orchestrator import Platform
from platform_agents.state_store import Conflict
from platform_agents.docker_adapter import SafetyError, WATCHDOG_SCRIPT, DockerAdapter, validate_probe


class FakeDocker:
    """Only in tests: clock-driven independent watchdog and immutable fake IDs."""
    def __init__(self, clock):
        self.clock = clock
        self.ids = {"api": "a" * 64, "web": "b" * 64}
        self.running = {value: True for value in self.ids.values()}
        self.starts, self.stops = [], []
        self.fingerprint = "original"
        self.ready = True
        self.fail_stop = None
        self.fail_start = False
        self.probes_healthy = True
        self.lease = None
        self.released = False

    def inspect(self, targets, required):
        return {"fingerprint": self.fingerprint, "containers": {name: {"id": self.ids[name]} for name in required}}

    def probe(self, components):
        ok = self.probes_healthy and all(self.running[self.ids[c]] for c in components)
        return [{"component": c, "purpose": p, "ok": ok, "timestamp": self.clock()} for c in components for p in ("readiness", "functionality", "dependency")]

    def arm(self, experiment_id, ids, deadline):
        self.lease = (ids, deadline)
        return "watchdog-synthetic"

    def watchdog_ready(self, *args):
        return self.ready

    def start_watchdog(self, watchdog_id):
        pass

    def stop(self, container_id):
        self.stops.append(container_id)
        if container_id == self.fail_stop:
            raise TimeoutError("synthetic-secret-must-not-escape")
        self.running[container_id] = False

    def start(self, container_id):
        self.starts.append(container_id)
        if self.fail_start:
            raise TimeoutError("synthetic-secret-must-not-escape")
        self.running[container_id] = True

    def states(self, ids):
        return {value: {"running": self.running[value], "health": "healthy" if self.running[value] else "unhealthy"} for value in ids}

    def abort(self, experiment_id):
        pass

    def release(self, *args):
        assert all(self.running.values())
        self.released = True

    def independent_tick(self):
        if self.lease and self.clock() >= self.lease[1]:
            for value in self.lease[0]:
                self.running[value] = True

    def close(self):
        pass


@pytest.fixture
def platform(store, tmp_path):
    now = [1000.0]
    source = {"component": "api", "finding_id": "synthetic-risk", "hypothesis": "Synthetic dependency hypothesis", "metrics": ["readiness"], "risk_score": 50}
    data = {"configuration_hash": "fixture-hash", "services": [{"name": n, "role": "application"} for n in ("api", "web")], "dependencies": [{"source": "web", "target": "api", "kind": "http"}], "recommendations": [source]}
    agent = SimpleNamespace(root=tmp_path, storage=store, latest=data, analyze=lambda *args: deepcopy(data))
    probes = [Probe(component=c, url=f"http://127.0.0.1:{8000+i}/health", required_text="ok", purpose=p) for i, c in enumerate(("api", "web")) for p in ("readiness", "functionality", "dependency")]
    policy = Policy(enabled=True, project="pfia-disposable-synthetic", compose_file=str(tmp_path / "compose.yml"), allowed_services=["api", "web"], max_targets=2, watchdog_verified=True, probes=probes, stability_seconds=2)
    adapter = FakeDocker(lambda: now[0])
    result = Platform(agent, policy, lambda: adapter, lambda: now[0])
    result.heartbeat()
    return result, adapter, now


def plan(p, targets=None, fault="container_stop"):
    return p.chaos.plan(PlanRequest(source_finding_id="synthetic-risk", targets=targets or ["api"], fault_type=fault, duration_seconds=5))


def approve(p, experiment):
    return p.approve(experiment.id, ApprovalRequest(proposal_hash=experiment.proposal_hash, confirmation="I APPROVE THIS EXACT EXPERIMENT"), "synthetic-operator")


def run(p, e):
    approve(p, e)
    p.execute(e.id)
    p.tick()
    return p.store.get(e.id)


def test_ingests_real_analysis_recommendations(checkout, store):
    agent = PredictiveAgent(checkout, store)
    p = Platform(agent)
    source = next(r for r in p.chaos.recommendations() if r["component"] == "api")
    e = p.chaos.plan(PlanRequest(source_finding_id=source["finding_id"], targets=["api"]))
    assert e.proposal.source_prediction == source
    assert e.state == "AWAIT_USER_APPROVAL"
    assert e.approval is None


def test_exact_approval_and_durable_pause(platform):
    p, fake, now = platform
    e = plan(p)
    p.tick()
    assert not fake.stops
    approve(p, e)
    reopened = Platform(p.agent, p.policy, lambda: fake, lambda: now[0])
    assert reopened.store.get(e.id).state == "APPROVED"
    assert reopened.store.get(e.id).approval["proposal_hash"] == e.proposal_hash
    with pytest.raises(SafetyError):
        p.approve(e.id, ApprovalRequest(proposal_hash="0" * 64, confirmation="I APPROVE THIS EXACT EXPERIMENT"), "operator")


def test_unapproved_and_expired_cannot_execute(platform):
    p, fake, now = platform
    e = plan(p)
    with pytest.raises(SafetyError):
        p.execute(e.id)
    approve(p, e)
    now[0] += 121
    p.heartbeat()
    with pytest.raises(SafetyError):
        p.execute(e.id)
    assert not fake.stops


@pytest.mark.parametrize("change", ["environment", "policy", "source"])
def test_approval_invalidates_on_change(platform, change):
    p, fake, now = platform
    e = plan(p)
    approve(p, e)
    if change == "environment":
        fake.fingerprint = "changed"
    elif change == "policy":
        p.policy.max_duration_seconds = 4
    else:
        p.agent.analyze = lambda *args: {**p.agent.latest, "configuration_hash": "changed"}
    with pytest.raises(SafetyError):
        p.execute(e.id)
    assert p.store.get(e.id).state == "INVALIDATED"
    assert not fake.stops


@pytest.mark.parametrize("fault", ["database_outage", "network_latency", "packet_loss", "cpu_stress", "memory_pressure"])
def test_unverified_adapters_are_unsupported(platform, fault):
    p, fake, now = platform
    e = plan(p, fault=fault)
    assert e.state == "UNSUPPORTED" and e.proposal.unsupported_reason
    with pytest.raises(SafetyError):
        approve(p, e)
    assert not fake.stops


@pytest.mark.parametrize("restriction", ["allowlist", "duration", "watchdog", "disabled", "probes", "worker", "kill_switch"])
def test_safety_restrictions(platform, restriction):
    p, fake, now = platform
    if restriction == "allowlist":
        p.policy.allowed_services = ["web"]
    if restriction == "duration":
        p.policy.max_duration_seconds = 1
    if restriction == "watchdog":
        p.policy.watchdog_verified = False
    if restriction == "disabled":
        p.policy.enabled = False
    if restriction == "probes":
        p.policy.probes = []
    if restriction == "worker":
        now[0] += 20
    if restriction == "kill_switch":
        (p.control_root / "STOP").touch()
    e = plan(p)
    with pytest.raises(SafetyError):
        approve(p, e)
    assert not fake.stops


def test_rejection_and_cancel(platform):
    p, fake, now = platform
    first = plan(p)
    assert p.reject(first.id).state == "REJECTED"
    second = plan(p)
    assert p.abort(second.id).state == "CANCELLED"
    with pytest.raises((SafetyError, Conflict)):
        approve(p, second)
    assert not fake.stops


def test_concurrent_experiments_rejected(platform):
    p, fake, now = platform
    first, second = plan(p), plan(p)
    approve(p, first)
    approve(p, second)
    p.execute(first.id)
    with pytest.raises(Conflict):
        p.execute(second.id)


def test_mocked_end_to_end_functional_recovery_and_feedback(platform):
    p, fake, now = platform
    e = run(p, plan(p))
    assert e.state == "OBSERVE" and len(fake.stops) == 1
    p.tick()  # Diagnosis must not prematurely reverse the fault.
    assert not fake.starts
    now[0] += 6
    p.tick()
    p.tick()
    assert fake.starts
    p.tick()
    now[0] += 12
    p.tick()
    result = p.store.get(e.id)
    assert result.state == "COMPLETED"
    assert all(result.report["verification"]["layers"].values())
    assert result.report["weakness_fixed"] is False
    assert fake.released
    assert p.agent.storage.read("experiment_feedback")[0]["risk_score_adjustment"] == 0


def test_emergency_abort_does_not_wait_for_deadline(platform):
    p, fake, now = platform
    e = run(p, plan(p))
    p.abort(e.id)
    assert (p.control_root / e.id / "ABORT").exists()
    p.tick()
    p.tick()
    assert fake.starts


def test_partial_multiple_stop_rolls_back_all_original_ids(platform):
    p, fake, now = platform
    fake.fail_stop = fake.ids["web"]
    e = run(p, plan(p, ["api", "web"], "multi_container_stop"))
    assert e.state == "FAILED_RECOVERY"
    p.tick()
    assert set(fake.starts) == set(fake.ids.values())
    assert not fake.released
    assert "synthetic-secret" not in str(p.store.events())


def test_orchestrator_crash_does_not_reinject_and_watchdog_expires(platform):
    p, fake, now = platform
    e = run(p, plan(p))
    # Simulated independent watchdog clock, not a live process-death verification.
    now[0] += 6
    fake.independent_tick()
    assert all(fake.running.values())
    p.store.change(e.id, {"OBSERVE"}, lambda current: setattr(current, "state", "INJECTING"))
    restarted = Platform(p.agent, p.policy, lambda: fake, lambda: now[0])
    restarted.tick()
    assert len(fake.stops) == 1
    assert fake.starts


def test_container_running_is_not_functional_recovery(platform):
    p, fake, now = platform
    e = run(p, plan(p))
    now[0] += 6
    p.tick()
    p.tick()
    fake.probes_healthy = False
    now[0] += 61
    p.tick()
    current = p.store.get(e.id)
    assert current.state == "FAILED_RECOVERY"
    assert not current.report["verification"]["layers"]["functionality"]
    assert not fake.released
    with pytest.raises(Conflict):
        p.store.change(plan(p).id, {"AWAIT_USER_APPROVAL"}, lambda e: setattr(e, "state", "QUEUED"), exclusive=True)


def test_immutable_proposal_cannot_be_mutated(platform):
    p, fake, now = platform
    e = plan(p)
    with pytest.raises(Conflict):
        p.store.change(e.id, {e.state}, lambda current: setattr(current.proposal, "duration_seconds", 30))


@pytest.mark.parametrize("url", ["http://example.com:80/hc", "http://127.0.0.1:80/hc?token=secret", "http://user:pass@localhost:80/hc", "https://localhost:443/hc", "http://localhost/hc"])
def test_probe_ssrf_and_credentials_rejected(url):
    with pytest.raises(SafetyError):
        validate_probe(Probe(component="api", purpose="functionality", url=url, required_text="ok"))


def test_watchdog_script_has_bounded_calls_and_independent_abort():
    assert "timeout 4 docker start" in WATCHDOG_SCRIPT
    assert "/global-control/STOP" in WATCHDOG_SCRIPT
    assert "/control/ABORT" in WATCHDOG_SCRIPT
    assert "Groq" not in WATCHDOG_SCRIPT
    assert "[ -f /control/RELEASE ]" in WATCHDOG_SCRIPT


def test_api_operator_authorization_and_mocked_workflow(platform, monkeypatch):
    p, fake, now = platform
    monkeypatch.setenv("PFIA_OPERATOR_TOKEN", "synthetic-operator-token-32-characters")
    app = create_app(p.agent)
    with TestClient(app) as client:
        app.state.platform = p
        body = {"source_finding_id": "synthetic-risk", "targets": ["api"], "duration_seconds": 5}
        assert client.post("/api/chaos/experiments/plan", json=body).status_code == 401
        headers = {"Authorization": "Bearer synthetic-operator-token-32-characters"}
        result = client.post("/api/chaos/experiments/plan", json=body, headers=headers)
        assert result.status_code == 200
        e = result.json()
        prefix = "/api/chaos/experiments/" + e["id"]
        assert client.post(prefix + "/execute", json={}, headers=headers).status_code == 409
        assert client.post(prefix + "/approve", json={"proposal_hash": e["proposal_hash"], "confirmation": "I APPROVE THIS EXACT EXPERIMENT"}, headers=headers).status_code == 200
        assert client.post(prefix + "/execute", json={}, headers=headers).status_code == 200
        p.tick()
        for path in ["/api/agents/status", "/api/chaos/experiments", prefix + "/status", "/api/healing/incidents", "/api/healing/incidents/" + e["id"], "/api/healing/actions", "/api/healing/history", "/api/chaos/reports"]:
            response = client.get(path)
            assert response.status_code == 200
            assert "synthetic-operator-token" not in response.text
        assert client.post(prefix + "/abort", json={}, headers=headers).status_code == 200


def test_missing_auth_configuration_denies_operations(checkout, store, monkeypatch):
    monkeypatch.delenv("PFIA_OPERATOR_TOKEN", raising=False)
    with TestClient(create_app(PredictiveAgent(checkout, store))) as client:
        assert client.post("/api/chaos/experiments/plan", json={"source_finding_id": "x", "targets": ["api"]}).status_code == 503
        assert client.get("/api/agents/status").json()["chaos"] == "execution disabled"


def test_real_project_policy_cannot_enable():
    with pytest.raises(ValueError):
        Policy(enabled=True, project="src", compose_file="compose.yml", allowed_services=["rabbitmq"])


def test_watchdog_not_ready_prevents_fault(platform):
    p, fake, now = platform
    fake.ready = False
    e = run(p, plan(p))
    assert not fake.stops
    assert e.state == "FAILED_RECOVERY"
    assert e.execution["watchdog_id"] == "watchdog-synthetic"


def test_probe_threshold_aborts_before_planned_deadline(platform):
    p, fake, now = platform
    p.policy.max_failed_probes = 0
    e = run(p, plan(p))
    p.tick()
    assert p.store.get(e.id).state == "RECOVERING"
    assert now[0] < e.execution["deadline"]


def test_worker_approval_expiration(platform):
    p, fake, now = platform
    e = plan(p)
    approve(p, e)
    now[0] += 121
    p.tick()
    assert p.store.get(e.id).state == "EXPIRED"


def test_recovery_retries_are_bounded(platform):
    p, fake, now = platform
    e = run(p, plan(p))
    fake.fail_start = True
    now[0] += 6
    for _ in range(12):
        p.tick()
        now[0] += 61
    assert len(fake.starts) == 3
    assert p.store.get(e.id).state == "FAILED_RECOVERY"
    assert not fake.released


def test_groq_failure_preserves_plan_and_does_not_grant_approval(platform, monkeypatch):
    p, fake, now = platform
    monkeypatch.setenv("PFIA_ENABLE_GROQ", "true")
    import platform_agents.reasoning as reasoning
    monkeypatch.setattr(reasoning, "GroqReasoner", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic-provider-key")))
    e = plan(p)
    assert e.state == "AWAIT_USER_APPROVAL" and e.approval is None
    assert not fake.stops
    assert "synthetic-provider-key" not in str(p.store.events())


def test_analysis_feedback_is_configuration_scoped_and_noncompounding(checkout, store):
    agent = PredictiveAgent(checkout, store)
    baseline = agent.analyze()
    original = next(r["score"] for r in baseline["weak_nodes"] if r["component"] == "api")
    row = {"experiment_id": "synthetic-feedback", "configuration_hash": baseline["configuration_hash"], "components": ["api"], "functional_recovery_verified": False, "risk_score_adjustment": 5}
    store.save("experiment_feedback", row)
    store.save("experiment_feedback", row)
    result = agent.analyze()
    risk = next(r for r in result["weak_nodes"] if r["component"] == "api")
    assert risk["score"] == min(100, original + 5)
    assert risk["experiment_evidence"]["matching_runs"] == 2
    assert risk["experiment_evidence"]["score_adjustment"] == 5
    (checkout / "src/Api/Program.cs").write_text("// changed source configuration")
    changed = agent.analyze()
    assert all(r["experiment_evidence"]["score_adjustment"] == 0 for r in changed["weak_nodes"])


def test_docker_constructor_failure_is_visible_and_bounded(platform):
    p, fake, now = platform
    e = run(p, plan(p))
    calls = []
    def unavailable():
        calls.append(True)
        raise TimeoutError("synthetic-docker-secret")
    p.adapter_factory = unavailable
    for _ in range(6):
        p.tick()
    current = p.store.get(e.id)
    assert current.state == "FAILED_RECOVERY"
    assert len(calls) == 3
    assert current.execution["watchdog_id"] == "watchdog-synthetic"
    assert (p.control_root / e.id / "ABORT").exists()
    assert "synthetic-docker-secret" not in str(p.store.events())
