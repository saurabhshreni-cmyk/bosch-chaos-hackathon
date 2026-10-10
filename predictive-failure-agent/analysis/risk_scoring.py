import networkx as nx
import math
from agent.schemas import Risk

DEFAULT_WEIGHTS = {"criticality": 25, "single_replica": 20, "missing_controls": 20, "static_findings": 15, "resource_pressure": 10, "health_anomalies": 10}


def score(services, graph, findings, metrics, weights=None):
    weights = DEFAULT_WEIGHTS if weights is None else weights
    if set(weights) != set(DEFAULT_WEIGHTS) or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()) or abs(sum(weights.values()) - 100) > .001:
        raise ValueError("Risk weights must have the documented six keys, be nonnegative and sum to 100")
    results = []
    for service in services:
        samples = [m for m in metrics if m.component == service.name]
        affected = sorted(nx.ancestors(graph, service.name))
        missing = ["Request throughput/capacity", "Queue depth and database pool/query telemetry", "Business workflow health", "Host placement and external redundancy", "Effective reconnect, acknowledgment, idempotency and worker-concurrency behavior", "DNS reliability and packet loss"]
        factors = {"criticality": len(affected) / max(1, len(services)-1), "single_replica": float(service.replicas == 1), "missing_controls": sum([not bool(service.limits), not service.healthcheck, service.restart == "not configured"]) / 3, "static_findings": min(1, sum({"low": .1, "medium": .25, "high": .5}[f.severity] for f in findings if f.component == service.name and f.status != "verified configuration"))}
        if samples:
            # Memory pressure needs a configured limit; CPU% of one core is not capacity.
            known_memory = [m.memory_bytes / m.configured_memory_limit for m in samples if m.configured_memory_limit]
            if known_memory:
                factors["resource_pressure"] = min(1, max(known_memory))
            else:
                missing.append("Configured memory limit and CPU capacity")
            factors["health_anomalies"] = float(any(m.health == "unhealthy" or m.state in {"exited", "dead", "restarting"} or m.restart_count > 0 for m in samples))
            missing.append("Sufficient history for trend inference (current observations only)")
        else:
            missing.append("Runtime metrics and historical health")
        known_weight = sum(weights[key] for key in factors)
        value = sum(weights[key] * v for key, v in factors.items()) / max(known_weight, 1) * 100
        # Coverage reports scored dimensions only, not a statistical confidence.
        component_findings = sorted([f for f in findings if f.component == service.name], key=lambda f: {"high": 0, "medium": 1, "low": 2}[f.severity])
        results.append(Risk(component=service.name, score=round(value, 1), evidence_coverage=known_weight/100, factors=factors, missing_evidence=missing, affected_dependents=affected, primary_concerns=[f.title for f in component_findings], dependencies=sorted(graph.successors(service.name)), supporting_evidence=[e for f in component_findings for e in f.evidence], failure_scenarios=list(dict.fromkeys(f.scenario for f in component_findings)), mitigations=list(dict.fromkeys(f.mitigation for f in component_findings))))
    return sorted(results, key=lambda r: (-r.score, r.component))
