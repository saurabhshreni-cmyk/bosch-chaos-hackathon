def recommendations(findings, risks):
    """Data only. These records have no experiment ID, executable payload or runner."""
    result = []
    by_component = {r.component: r for r in risks}
    for finding in findings:
        if finding.severity == "low":
            continue
        risk = by_component[finding.component]
        verification = "Reproduce the suspected dependency/resource condition in a disposable clone with synthetic data, then compare baseline, impact and application-level recovery."
        if finding.component == "rabbitmq" or "prefetch" in finding.title.lower():
            verification = "In a disposable clone, test a bounded broker outage or capped synthetic queue backlog; measure publisher errors, consumer reconnects, backlog drain and business-message consistency after recovery."
        elif finding.component == "sqlserver" or "database" in finding.title.lower():
            verification = "Use a disposable database and synthetic rows to test bounded database unavailability; check request results, connection recovery and event/data consistency."
        elif "timeout" in finding.title.lower() or "retry" in finding.title.lower():
            verification = "Use a stub dependency with bounded delay/errors in an isolated test to verify total timeout, retry count, backoff and fallback behavior."
        elif "replica" in finding.title.lower() or "restart" in finding.title.lower():
            verification = "In an authorized disposable clone, terminate one allowlisted container for a bounded interval and verify independent recovery and completed business workflows."
        result.append({"component": finding.component, "finding_id": finding.id, "risk_score": risk.score, "evidence_coverage": risk.evidence_coverage, "possible_root_cause": finding.evidence[0].description, "supporting_evidence": [e.model_dump() for e in finding.evidence], "relevant_dependencies": risk.dependencies, "potential_downstream_impact": risk.affected_dependents, "hypothesis": finding.scenario, "mitigation": finding.mitigation, "proposed_verification": verification, "metrics": ["request latency and errors", "business workflow completion", "queue backlog where authorized", "reconnect and recovery time"], "safety": ["Separate environment authorization", "Explicit target allowlist", "Bounded duration", "Independent automatic recovery", "Human approval and kill switch"], "executable": False})
    return result
