"""Conservative C# lexical checks, not a compiler or whole-program proof."""
import hashlib
import re
from agent.schemas import Evidence, Finding


def analyze_code(root, services):
    findings = []
    def add(service, title, path, line, description, scenario, mitigation, severity="medium", verified=False):
        findings.append(Finding(id=hashlib.sha256(f"{service.name}:{path}:{line}:{title}".encode()).hexdigest()[:16], component=service.name, title=title, severity=severity, status="verified configuration" if verified else "evidence-supported hypothesis", evidence=[Evidence(path=path, line=line, description=description)], scenario=scenario, mitigation=mitigation))
    for service in services:
        compose_lines = (root / "src/docker-compose.yml").read_text(encoding="utf-8-sig").splitlines()
        compose_line = next((i for i, row in enumerate(compose_lines, 1) if re.match(rf"  {re.escape(service.name)}:\s*$", row)), 1)
        for condition, title, explanation in [(not service.limits, "No Compose resource limits", "Container-level CPU/memory caps are absent from this Compose file; engine or host policy is unknown."), (service.replicas == 1, "Single configured replica", "One replica is configured; external redundancy or host placement is unknown."), (not service.healthcheck, "No discovered health check", "No Compose or application health check was discovered."), (service.restart == "not configured", "No Compose restart policy", "Automatic restart is not configured in the Compose service.")]:
            if condition:
                add(service, title, "src/docker-compose.yml", compose_line, explanation, "Container or host pressure can interrupt service; validate deployed settings.", "Review resource budgets, redundancy, readiness and restart policy.", verified=True)
        csfiles = [p for p in service.code_paths if p.endswith(".cs")]
        own_text = "\n".join((root / p).read_text(encoding="utf-8-sig", errors="replace") for p in csfiles if "/Infrastructure.Messaging/" not in p)
        csfiles = [p for p in csfiles if not (p.endswith("RabbitMQMessageHandler.cs") and not re.search(r"IMessageHandler|UseRabbitMQMessageHandler", own_text)) and not (p.endswith("RabbitMQMessagePublisher.cs") and not re.search(r"IMessagePublisher|UseRabbitMQMessagePublisher", own_text))]
        joined = "\n".join((root / p).read_text(encoding="utf-8-sig", errors="replace") for p in csfiles)
        for path in csfiles:
            text = (root / path).read_text(encoding="utf-8-sig", errors="replace")
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith("//"):
                    continue
                if "AddHttpClient<" in line and not re.search(r"\.Timeout\s*=", joined):
                    add(service, "No explicit HTTP timeout discovered", path, i, "Typed HttpClient registration without a discovered explicit Timeout assignment; framework defaults still apply.", "Slow dependencies can hold requests through default timeout and retries.", "Measure latency and set bounded per-request timeout/cancellation budgets.")
                if re.search(r"\.RetryAsync\(\d+\)", line):
                    add(service, "Immediate retries may amplify dependency pressure", path, i, "Fixed-count RetryAsync has no delay argument at this call site.", "A degraded dependency can receive multiple immediate attempts per user request.", "Use bounded backoff with jitter and evaluate a circuit breaker.")
                if "AddHealthChecks();" in line:
                    add(service, "Health registration has no dependency checks at this site", path, i, "Bare AddHealthChecks registration; other registrations may exist.", "A responsive process may still be unable to complete business workflows.", "Distinguish liveness from dependency-aware readiness and business health.", severity="low")
                if "WaitAndRetry(" in line:
                    add(service, "Blocking retry policy requires budget review", path, i, "Synchronous WaitAndRetry call found; duration and startup/request context require review.", "Dependency outage may block startup or workers longer than callers expect.", "Verify total retry budget and cancellation propagation.", severity="low")
                if re.search(r"\basync\s+void\s+(?:Stop|Dispose|Close)\s*\(", line):
                    add(service, "Asynchronous lifecycle method cannot be awaited", path, i, "async void lifecycle method found in compiled/project-referenced source; runtime call reachability is not proven.", "Callers may finish shutdown before cleanup completes; asynchronous exceptions may escape the caller.", "Review lifecycle ownership, use awaitable Task methods, and test cancellation and broker disconnection in isolation.")
                if "BasicConsumeAsync(" in line and "BasicQos" not in joined:
                    add(service, "No explicit consumer prefetch discovered", path, i, "Consumer registration found without BasicQos in inspected source; effective broker/client defaults are unknown.", "Backlog and slow handlers could accumulate deliveries or pressure consumers, depending on effective flow control.", "Inspect effective prefetch and consumer concurrency; measure backlog and memory with synthetic messages in isolation.", severity="low")
                if "RetryForever" in line:
                    add(service, "Unbounded retry policy found", path, i, "RetryForever call found; cancellation and call reachability need inspection.", "An unavailable dependency can hold a worker indefinitely without an effective cancellation budget.", "Use a bounded total retry duration and propagate cancellation.", severity="high")
                if re.search(r"(?:HttpClient|WebRequest|SqlConnection)\s*\(", line) and "new " in line and "using" not in line:
                    add(service, "External connection lifetime needs review", path, i, "Connection/client creation without using syntax on this line; disposal elsewhere may be correct.", "Repeated creation without disposal can consume sockets or database connections.", "Inspect ownership and disposal across all exit paths.", severity="low")
                if "BasicConsume" in line and re.search(r"(?:true|autoAck\s*:\s*true)", line):
                    add(service, "Automatic message acknowledgments need review", path, i, "Consume call appears to enable automatic acknowledgments; verify overload and deployed library.", "A consumer crash during processing may lose work that was already acknowledged.", "Use manual acknowledgments after durable processing and test idempotency in isolation.")
                if re.search(r"(?:Task\.Run|Parallel\.ForEach)\(", line) and not re.search(r"(?:SemaphoreSlim|MaxDegreeOfParallelism|BoundedChannel)", joined):
                    add(service, "Worker concurrency bounds not established", path, i, "Parallel/task launch found without a recognized bound in this service; this is not proof of unbounded work.", "Bursty workloads may exhaust worker or downstream capacity.", "Trace task lifetime and measure concurrency before setting bounded work queues.", severity="low")
    known = root / "docs/publish-integrity.md"
    customer = next((s for s in services if s.name == "customermanagementapi"), None)
    if known.exists() and customer:
        add(customer, "Known database write and event publication divergence", "docs/publish-integrity.md", 1, "Repository documents a committed customer row followed by failed broker publication and HTTP 500. This is an existing defect, not newly verified by PFIA.", "RabbitMQ outage can leave committed customer data without its event; broker restoration does not repair it.", "Track the known integrity defect separately; verify only with disposable databases and synthetic data. PFIA does not change business semantics.", severity="high")
    return findings
