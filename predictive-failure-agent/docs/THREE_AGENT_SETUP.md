# Three-agent platform: setup and operating limits

PFIA remains the analysis agent. ChaosInjectionAgent consumes its actual recommendations.
SelfHealingAgent restores original container IDs and records functional verification.
Neither the existing C# dashboard nor application/PowerShell files are modified.

## Windows PowerShell

From the repository root:

```powershell
Set-Location .\predictive-failure-agent
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path storage\chaos-policy.local.json)) { Copy-Item chaos-policy.example.json storage\chaos-policy.local.json }
$env:PFIA_POLICY_FILE = (Resolve-Path storage\chaos-policy.local.json).Path
$env:PFIA_OPERATOR_TOKEN = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8091
```

Keep the operator token private and enter it in the dashboard password field. Configure
Groq privately in `.env` using the existing instructions; no key is required for deterministic
operation. Keep the backend terminal open. In a second terminal in the project directory:

```powershell
$env:PFIA_POLICY_FILE = (Resolve-Path storage\chaos-policy.local.json).Path
.\.venv\Scripts\python.exe -m platform_agents.worker
```

In a third terminal in the same directory:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true
```

Open `http://127.0.0.1:8502`; API docs: `http://127.0.0.1:8091/docs`.
Backend and worker must share the same checkout, SQLite database and policy file.
Only the backend needs the operator token. Local authorization supports one operator,
not a multi-user identity service. Bind services to loopback.

## Safety policy

The supplied policy has `enabled: false` and `watchdog_verified: false` deliberately.
Planning works without enabling execution. Before enabling, separately authorize and
verify a disposable test environment with these conditions:

- Compose project named `pfia-disposable-*`; normal Pitstop `src` is forbidden.
- Resolved Compose YAML path, explicit service allowlist and matching Compose ownership
  labels. Every affected service must have label `pfia.disposable: "true"`.
- Targets are single running containers without persistent volumes, host binds,
  privileged mode, host networking or Docker socket access. Database targets are unsupported.
- Every affected container uses project-owned internal bridge networks, with no foreign
  peers or host aliases. Published ports bind only to loopback. A renamed container or
  disposable label on a network shared with normal Pitstop is insufficient isolation.
- Every affected service has operator-validated local published-port GET probes for
  `readiness`, `dependency` and `functionality`, each with required success text. Schema
  example: `{"component":"webapp","url":"http://127.0.0.1:15100/Health","required_text":"Healthy","purpose":"readiness"}`.
  This illustrates syntax, not an assertion that this route exists. Use verified routes.
  Dependency probes must actually exercise the relevant connection. A generic liveness
  check incorrectly labeled by an operator cannot establish consumer reconnection.
- Reviewed existing local `docker:cli` image containing `sh`, `timeout`, `date` and Docker CLI.
  The executor never pulls images. Linux containers and Docker Desktop sharing of the
  control directory are required. The watchdog mounts the Docker socket with daemon-level
  authority despite its other restrictions. Use only a disposable local Docker environment.
- Separately approved disposable tests must demonstrate deadline rollback, forced worker
  termination, backend/terminal closure, STOP, Docker response failure and watchdog retention.
  Inspect actual target state and functional probes. Only then set `watchdog_verified: true`
  and enable the policy. **No such live verification was performed for this implementation.**

Policy limits: duration 1–60 seconds, at most two explicit targets, approval expiry 10–120
seconds, stability 2–30 seconds and failed-probe abort threshold 0–30. Default threshold 30
allows expected impact; zero aborts on the first failed probe. Restart backend and worker
after policy edits. Configuration, policy or container identity changes invalidate approval.
Docker's atomic per-project watchdog name also prevents overlap across separate databases.

## Approve, execute and observe

1. Run **Analyze Application** in PFIA Analysis.
2. Open **Chaos Engineering**, select a recommendation, targets, adapter and duration.
3. Click **Prepare proposal**. Review immutable contents, hash, blast radius and rollback.
4. Enter the operator token, check the exact-proposal approval checkbox, then click
   **Approve and Execute**. A recommendation alone never grants approval.
5. The backend validates the environment and baseline; the worker revalidates, persists
   original IDs, arms a watchdog and verifies its acknowledgement before injection.
6. Click **Refresh recorded state** to see progress. There is no automatic UI polling.

Implemented adapters: bounded single stop, explicit two-container stop, planned restart
(stop, observe, restore), and RabbitMQ outage using exact-ID stop/start. RabbitMQ targets
with persistent mounts are rejected. Network latency, packet loss, database outage, CPU
stress and memory pressure remain explicitly unsupported pending validated tools/rollback.

**Self-Healing** shows incidents, playbooks and verification. **Agent Collaboration** shows
timestamped deterministic events separately from AI hypotheses and token usage. **Experiment
History** shows approvals, accepted injection requests, original IDs, baselines, timing and reports.

## Emergency recovery

Use **Cancel / Emergency Stop** for an experiment. It writes ABORT before database updates
or Docker operations. If the backend is unavailable, from the project directory:

```powershell
New-Item -ItemType File -Force storage\chaos-control\STOP
```

This switch prevents new execution and is observed directly by watchdogs. For a single
known experiment, create `storage\chaos-control\<experiment-id>\ABORT` instead. Do not
delete STOP while recovery is unresolved. The worker additionally honors repository
`chaos-scripts/STOP`; the watchdog directly observes the platform control STOP.

The watchdog starts original IDs on deadline, ABORT, STOP or worker heartbeat older than
ten seconds. It retries until infrastructure restoration and explicit worker release.
It survives Python/Groq failure but cannot recover an unavailable Docker daemon or powered-off
host while they are down, recreate deleted targets, or repair business data.
Long worker stalls can trigger early rollback as a safety threshold.

The worker attempts at most three recovery passes. Ambiguous stop responses retain the lease
and watchdog for investigation. Failed recovery stays visible and blocks new experiments.
Do not remove a retained watchdog simply to clear a lease. Watchdog IDs are in experiment status.
The watchdog verifies infrastructure only; full recovery requires the worker's configured
readiness, dependency, functional and continuous stability checks. Container state alone is
never success. Probes cannot prove message delivery or data integrity without dedicated evidence.
Stability requires at least three healthy samples across the observation window. A gap
longer than `max_verification_gap_seconds` (default three seconds) resets that window;
time while the worker was not observing cannot be counted as verified stability.
Unexpected unhealthy containers are inspected read-only every 15 seconds in the authorized
environment; remediation is proposed and never auto-executed without separate authorization.

## Analysis feedback and Groq

Recorded outcomes supplement PFIA only for matching configuration hashes. Successful recovery
does not reduce static risk. A completed injection with restored infrastructure and persistent
failing functional probes adds at most five relative risk points. Runs do not compound the
adjustment. Evidence counts are separate from scoring-dimension coverage. This documented
heuristic is not a probability or causal proof.

The new agents reuse existing Groq structured-output validation, cache and bounded retry
implementation. Each explanation has at most three attempts including model listing. Usage
is tagged by agent/experiment. Groq never controls Docker arguments, approvals, timers or scores.
Missing keys, quota exhaustion and invalid output leave deterministic operation unchanged.

Known defect: RabbitMQ downtime can cause `POST /api/customers` HTTP 500 after the row commits
but before its event publishes. Restoring RabbitMQ does not repair that inconsistency. No outbox,
queue purge or business-data changes are included.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests are unit, mocked infrastructure/provider, in-process FastAPI and Streamlit AppTest.
Real network and Docker access are blocked by the autouse fixture. Coverage includes approvals,
expiry, immutable hashes, safety restrictions, partial execution, cancellation, mocked watchdog
expiry/process restart, functional verification, adapter SDK contracts and all dashboard pages.

Not live-verified: fault injection, watchdog shell execution/process-death recovery, Desktop
bind sharing, dependency reconnection, message delivery, business-data integrity, Groq or browser
visual layout. No destructive integration test was run against normal Pitstop. Keep execution
disabled until the separately approved disposable verification is completed.
