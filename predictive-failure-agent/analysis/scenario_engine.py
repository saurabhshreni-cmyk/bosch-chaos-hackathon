from analysis.cascade_analysis import cascade


def evaluate(request, services, graph, metrics):
    names = {s.name for s in services}
    if request.target and request.target not in names:
        raise ValueError("Unknown target; choose a discovered service")
    defaults = {"database": "sqlserver", "broker": "rabbitmq"}
    target = request.target or defaults.get(request.kind)
    if request.kind in {"database", "broker"}:
        expected = defaults[request.kind]
        if target != expected or expected not in names:
            raise ValueError(f"{request.kind} scenario requires discovered {expected}")
    if request.kind in {"cascade", "container"} and not target:
        raise ValueError("This scenario requires a discovered target")
    impacts = cascade(graph, target) if target else []
    assumptions = ["Hypothetical analytical scenario. No fault, traffic or resource load was generated.", "Dependency presence does not establish complete endpoint unavailability."]
    detail = ""
    if request.kind == "traffic":
        detail = f"{request.traffic_multiplier}x hypothetical request volume. No measured capacity/throughput curve: failure threshold cannot be calculated."
        impacts = [{"component": s.name, "impact": "Review request concurrency, retries, database pools and queue processing capacity."} for s in services if s.role == "application" and (not target or s.name == target)]
    elif request.kind == "database":
        detail = "Database-dependent operations may fail or wait for retry budgets; connection pool limits and recovery are not measured."
    elif request.kind == "broker":
        detail = "Publishing may fail and consumers may disconnect. Backlog, acknowledgments, persistence and reconnect behavior require isolated verification."
        assumptions.append("Known Pitstop limitation: POST /api/customers can commit a row then return 500 if event publication fails. Broker restoration does not repair the missing event.")
    elif request.kind == "network":
        detail = f"Hypothetical +{request.latency_ms} ms per dependency interaction, {request.packet_loss_percent}% loss. Call counts, retry distributions and concurrency are unknown; no end-to-end latency forecast."
        impacts = [{"component": name, "impact": "Dependency latency may amplify request or message-processing time.", "outbound_dependencies": graph.out_degree(name)} for name in graph if graph.out_degree(name) and (not target or name == target)]
    elif request.kind == "resource":
        detail = "CPU, memory and worker exhaustion are qualitative risks. Current samples do not establish future saturation or memory growth."
        impacts = [{"component": s.name, "impact": "Missing resource budget" if not s.limits else "Configured budget requires capacity validation", "observed_cpu_percent_one_core": next((m.cpu_percent for m in metrics if m.component == s.name), None), "observed_memory_bytes": next((m.memory_bytes for m in metrics if m.component == s.name), None)} for s in services if not target or s.name == target]
    elif request.kind == "host":
        detail = "Host placement is unknown. A shared-host outage could affect every co-located container; exact placement cannot be inferred from Compose."
        assumptions.append("No verified multi-host placement or redundancy evidence.")
    else:
        detail = "Loss may propagate against consumer-to-dependency edges. Fallbacks can reduce impact; evaluate business operations separately."
    if target and request.kind in {"database", "broker", "container", "cascade"}:
        impacts.insert(0, {"component": target, "path": [target], "impact": "Hypothetically unavailable; not an observed outage."})
    return {"kind": request.kind, "target": target, "parameters": request.model_dump(), "evidence_class": "hypothetical analysis", "detail": detail, "impacts": impacts, "assumptions": assumptions}
