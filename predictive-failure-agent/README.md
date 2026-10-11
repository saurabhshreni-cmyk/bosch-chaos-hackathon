# Predictive Failure Intelligence Agent (PFIA)

The optional three-agent extension adds restricted chaos planning, expiring operator approval,
independent watchdog rollback and self-healing evidence. Execution is disabled by default.
See [three-agent setup](docs/THREE_AGENT_SETUP.md) and [integration contract](docs/THREE_AGENT_INTEGRATION.md).

PFIA inspects the existing Pitstop checkout, builds an evidence-linked dependency
graph, ranks relative engineering risks and evaluates hypothetical failures.
Three specialized agents share a FastAPI API and a Streamlit dashboard. The existing
C# dashboard and chaos scripts remain separate and unchanged.

**The analysis agent remains read-only.** Its metrics adapter uses list, inspect and stats.
Recommendations are non-executable records. The separate chaos executor requires an
authenticated, expiring approval, validated disposable policy and independent watchdog.
Groq narrative cannot set scores, issue commands, change graph edges or establish recovery.

## Windows PowerShell setup

Prerequisites: Python 3.11 or later (verified with 3.13.12), Git, and Docker
Desktop with Linux containers only if runtime observations are wanted.
The repository's existing Pitstop stack must already be running to collect
metrics. PFIA never starts it. No API key is required for deterministic analysis.

From the repository root:

```powershell
Set-Location predictive-failure-agent
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
& .\.venv\Scripts\python.exe -m pytest -q
```

`requirements.txt` permits compatible versions; `requirements-lock.txt` records
the exact fresh-environment versions used for verification. To reproduce those
versions, install `-r requirements-lock.txt` instead.

In terminal 1, from `predictive-failure-agent`:

```powershell
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8091
```

In terminal 2, from the same directory:

```powershell
& .\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
```

Open http://127.0.0.1:8502 and click **Analyze Application**.
API documentation: http://127.0.0.1:8091/docs. Stop each PFIA process with Ctrl+C.
Stopping PFIA requires no rollback because it applies no fault.

## Optional read-only runtime observations

Get the existing Compose project label, without displaying container environment:

```powershell
docker inspect webapp --format '{{index .Config.Labels "com.docker.compose.project"}}'
```

Set `PFIA_DOCKER_PROJECT` to that value in PFIA's own `.env`, and set
`PFIA_COLLECT_RUNTIME=true`. The verified local project label was `src`; do not
assume another checkout uses it. Restart the backend, select runtime collection
and analyze. Collection is limited to discovered services with that project label
on the local engine. `DOCKER_HOST` is deliberately ignored.

Enabled runtime collection also starts a sampler, with `PFIA_SAMPLE_INTERVAL`
seconds between completed analyses (minimum 15). It never calls Groq. Docker
stats requests have a three-second timeout; health GETs have a two-second timeout,
run serially, and use discovered local published ports and source health paths.
No business POSTs, SQL queries or broker-management requests are made.

Manual read-only verification, separate from the automated suite:

```powershell
$env:PFIA_COLLECT_RUNTIME = 'true'
$env:PFIA_DOCKER_PROJECT = 'src' # replace with your verified existing label
& .\.venv\Scripts\python.exe -m tools.verify_readonly --runtime
```

This records metrics and health plus before/after container start times and
restart counts in ignored `storage/verification.json`. Unchanged lifecycle
metadata is an observation, not proof that no external activity occurred.

## Optional Groq reasoning

Edit only PFIA's ignored `.env` locally. Never copy another application's `.env`.
Set `GROQ_API_KEY` to your own key and `PFIA_ENABLE_GROQ=true`. Defaults:

```dotenv
GROQ_FAST_MODEL=openai/gpt-oss-20b
GROQ_REASONING_MODEL=openai/gpt-oss-120b
LLM_MAX_OUTPUT_TOKENS=1024
LLM_MAX_CALLS_PER_ANALYSIS=15
LLM_TEMPERATURE=0.1
```

Restart the backend, enable **Use Groq explanations**, then analyze. The fast
model explains configuration findings; the reasoning model reviews combined
scenarios. A model-list request verifies access before uncached completions.
Default uncached analysis uses one model-list request and two completions.
The call budget includes model listing and retry attempts; SDK retries are off.
429/500/502/503/504 may receive one retry after 0.5 seconds. Other errors, invalid
output and timeouts do not retry. Request timeout is 15 seconds.

Strict JSON Schema is used for the two default GPT-OSS models. Other configured
models use JSON-object output and the same strict local Pydantic validation.
Unsupported fields, incomplete output, invented components and missing/unknown
finding references are rejected. Provider details and authorization are never
logged. Only compact component names, finding IDs/titles and scenario summaries
are sent; source, configuration values and metric measurements stay local.

Narratives are cached by model, generation settings, compact evidence and source/
configuration hash. Cache hits make no API call. AI text is always labeled an
unverified hypothesis. Actual returned token usage is recorded even when output
is rejected. A provider failure leaves deterministic results available.

**Live Groq verification has not been performed for PFIA.** Automated provider
tests use synthetic providers and an official SDK with mocked HTTP transport.
An optional live check is successful only when AI Insights reports `available`
and `/api/llm-usage` records actual usage. A cached result or mocked test does not
constitute a live check. Do not enable Groq merely to run the automated suite.

## Evidence and scoring

Edges point from **consumer to dependency**. Availability effects traverse the
reverse graph. Startup ordering and logging are displayed but excluded from the
availability graph. Broker edges describe asynchronous processing, not proof
that all HTTP endpoints fail. Curated event topology has medium confidence.

`risk-weights.json` defines six nonnegative weights summing to 100. Each factor
is in [0,1]. Score = 100 Ã— sum(weight Ã— known factor) / sum(known weights).
Coverage = known weights / 100. Missing runtime evidence is omitted rather than
scored as healthy or risky. This normalization means scores with different
coverage should be compared cautiously. Coverage describes scored dimensions,
not statistical confidence or completeness of all operational evidence.

| Factor | Default weight | Deterministic rule |
| --- | ---: | --- |
| Criticality | 25 | Transitive dependent count / (service count âˆ’ 1) |
| Single replica | 20 | 1 for exactly one configured replica; external redundancy unknown |
| Missing controls | 20 | Fraction missing Compose limits, discovered health and restart policy |
| Static findings | 15 | Sum severity contributions low=.1, medium=.25, high=.5, capped at 1; config findings excluded to avoid double counting |
| Resource pressure | 10 | Maximum observed memory/configured limit ratio, capped at 1; absent without a configured limit |
| Health anomalies | 10 | 1 for observed unhealthy/exited/dead/restarting state or nonzero cumulative restart count; not a recent restart rate |

CPU percentage is relative to one core, can exceed 100, and does not establish
saturation without CPU capacity. Docker stats memory limits may be host limits;
they are displayed separately from configured container limits. Network values
are cumulative byte counters, not rates. Current samples are not a trend model.

SQLite retains records for `PFIA_RETENTION_DAYS` (default 7) and at most
`PFIA_MAX_SAMPLES` records across all kinds (default 10000). Cache entries expire
with the same retention window. Storage and environment files are gitignored.
Experiment leases, approvals and workflow events use separate durable tables and are
not removed by metric retention. See the setup guide for bounded experiment feedback scoring.

## Scope and limitations

- Static checks are conservative C# lexical/configuration checks, with paths and
  line numbers. They do not prove disposal, idempotency, reconnect behavior,
  circuit-breaker absence or defects across library boundaries. Current projects
  reference `src/Infrastructure.Messaging` directly and Dockerfiles copy it.
  Running image provenance and runtime call reachability remain unverified.
- Queue depth, database readiness/query/pool statistics, request error rates,
  worker capacity, packet loss and multi-host placement are currently missing
  evidence. PFIA does not invent them or query credentials to obtain them.
- Traffic 2x/5x/10x and network scenarios are qualitative without capacity/call
  measurements. No precise future failure threshold or calibrated probability
  is produced. Graph counts include shortest dependency reachability, not an
  exhaustive count of business-critical paths.
- Known defect remains: `POST /api/customers` can return 500 after committing a
  row when RabbitMQ publication fails. Restoring RabbitMQ does not repair the
  absent event. PFIA does not fix data semantics or implement an outbox.
- Bind the API/dashboard to loopback. This developer tool has no multi-user
  authentication and is not intended for public hosting.

See [architecture](docs/architecture.md) and
[verification progress](docs/implementation-progress.md).
