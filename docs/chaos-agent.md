# Local Chaos Agent

The controller in `agent/run-agent.ps1` captures a baseline, asks AI to choose a
registered experiment, validates its plan, runs fixed tools, verifies recovery,
and writes findings before choosing another experiment. It supports four
experiments, but does not need to run every listed failure example in the brief.

## Setup

Start Pitstop using the root README. Then, from the repository root:

```powershell
docker pull nicolaka/netshoot:v0.13
./agent/setup-ai.ps1
```

Setup starts [Ollama in Docker](https://docs.ollama.com/docker), restricted to
`127.0.0.1:11434`, and downloads [qwen2.5:1.5b](https://ollama.com/library/qwen2.5:1.5b).
The model is approximately 986 MB; the server image is another download. This
requires internet and disk space during setup, but inference runs locally.
The AI container is separate from the Pitstop Compose project, limited to two
CPUs and 3 GB RAM, and has no Docker socket or application database access.

## Plan and Execute

Preview AI-selected plans without injecting faults:

```powershell
./agent/run-agent.ps1
```

Run at most three AI-selected experiments:

```powershell
./agent/run-agent.ps1 -Execute -MaxExperiments 3
```

By default the controller collects a three-minute sequential-read baseline. It
checks healthy baseline content, not just HTTP 200. Each experiment also checks
a fresh baseline before injection. Fault scripts and the baseline collector share
a lock within this checkout; the agent also has a separate session lock.

Test the fixed orchestration without an AI model:

```powershell
./agent/run-agent.ps1 -RuleBased -Execute -MaxExperiments 3
```

Rule-based mode is explicitly labeled as **not AI** and never substituted
silently for a failed model. It uses the catalog order. AI mode requests a new
selection after each result; it aborts if a plan is invalid, inference fails,
recovery fails, or the experiment budget is exhausted.

To choose the available candidates:

```powershell
./agent/run-agent.ps1 -Execute -ExperimentIds workshop-crash,database-crash,workshop-delay
```

The AI selects an ID, a bounded duration, a reason, and expected impact. An
allowlist implemented in `AgentTools.psm1` determines the actual target and
failure action. Extra keys, shell commands, arbitrary targets, duplicate
experiments, and excessive or fractional durations are rejected. The controller
calls PowerShell scripts directly; it does not evaluate model-generated code.
Explanations are limited to 240 characters. A truncated or malformed JSON reply
gets one shorter retry; two incomplete replies abort that selection before any
fault is injected. An unsafe but complete plan is rejected without retry.
Before mutation, the runner verifies the container's Compose service and source
configuration labels match this checkout. Remote Docker endpoints are rejected.

## Experiments

| ID | Action | Independent rollback |
| --- | --- | --- |
| workshop-crash | Kill Workshop API | Restart the same container |
| database-crash | Kill SQL Server | Restart, retaining its data volume |
| rabbitmq-crash | Kill RabbitMQ | Restart, retaining its persistent storage |
| workshop-delay | Add 500 ms Workshop API egress latency | Remove only the script-owned traffic-control rule |

Network delay uses a [netshoot helper sharing the target network namespace](https://github.com/nicolaka/netshoot)
with `NET_ADMIN` to run Linux `tc`, without installing tools in the API image.
It modifies `eth0` egress in Workshop API only, refuses an existing non-default
root queue configuration, and owns handle `28:`. Outgoing SQL and broker traffic
can also be delayed, so page latency may increase by more than 500 ms. The helper
image must be downloaded before the experiment; downloads are not timed faults.

The shared runner restores after the configured duration, on two impacted
modules for a shared dependency, on unaffected-module failure/latency for Workshop
experiments, or on the `chaos-scripts/STOP` switch. Watchdog and cleanup do not
depend on AI. A forced host or PowerShell shutdown still requires manual cleanup.
STOP is checked between bounded probes, rather than continuously. The agent
stops before selecting further faults when STOP exists.

## Evidence and Reporting

`agent/runs/<session-id>/` contains `baseline.json`, `baseline.csv`, `session.json`,
and `findings.md`. Experiment reports and anomalies remain under
`chaos-scripts/results/<experiment-id>/`. Sessions record those paths and run IDs.
Generated evidence is ignored by Git; selected verified runs are retained in
`docs/evidence/day1/`. Save later submission runs separately. AI findings are
sorted by severity across the session.

AI receives the map, aggregate baseline measurements, catalog, prior summaries,
and anomaly evidence. It has no command-execution tools. Findings must cite
existing evidence IDs, distinguish hypotheses from facts, and recommend fixes.
Interpretations still require human review. No calibrated resilience score is
claimed, and this prototype does not automatically edit application code.
AI requests allow up to 180 seconds for CPU inference; fault deadlines do not
depend on these requests.

Read-page checks do not prove message durability, write correctness, or background
worker recovery. For RabbitMQ, record unique event IDs across tracked writes and
consumption before claiming message loss, duplication, or successful delivery.
All-four-catalog coverage still includes similar container-kill mechanisms;
discuss the shared-dependency and broker scenarios as distinct impacts rather
than claiming four entirely different injection mechanisms.

## Baseline Only

```powershell
./agent/baseline.ps1 -DurationSeconds 180
```

It reports sample counts, failures, error rates, median, and nearest-rank p95.
These are low-rate read measurements; timeout latencies are censored, and this
does not simulate production load. Do not run faults in another checkout during
the baseline; the file lock cannot coordinate different clones or machines.

## Stop and Validate

Create `chaos-scripts/STOP` in another terminal to restore an active experiment
and stop further planning. Remove it before a new session. If the host process
was forcibly terminated, restore the killed target with Compose. For interrupted
network delay, restart Workshop API to recreate its network namespace and check
that no `netem` queue remains before proceeding.

Stop the optional AI server, retaining downloaded models:

```powershell
docker compose -f agent/compose.ai.yml down
```

Focused validation:

```powershell
./agent/tests/plan-validation.tests.ps1
./agent/tests/planner-response.tests.ps1
./chaos-scripts/tests/analyze-anomalies.tests.ps1
./chaos-scripts/tests/stop-before-injection.tests.ps1
```

For a demo: show the dependency map and healthy baseline, the AI's chosen ID and
reason, injected impact, rollback and recovery, then the evidence-backed findings.
Dashboard and automatic fixes remain optional future work.

## Verified AI Run

On October 10, 2026, local `qwen2.5:1.5b` selected and validated a plan without
injecting faults in session `20261010T100757709Z`. An execution test in session
`20261010T101001857Z` then selected the sole allowed `workshop-delay` candidate,
injected a 20-second bounded delay, restored all three pages, and produced
AI findings citing the four measured anomalies. Recovery checking took 0.09 s.

See [saved findings](evidence/ai-live/findings.md) and
[raw analysis](evidence/ai-live/anomalies.json). The execution test used a short
five-second session baseline, not a production load test. The clean three-minute
baseline is separately retained in [Day 1 evidence](day1-evidence.md).

The first 60-second AI request timed out without injecting anything. The current
configuration uses two inference threads and a 180-second timeout. The small
model initially gave generic explanations, including an incorrect suggestion
that injecting a fault improves performance. The planner prompt now explicitly
asks for expected degradation; analysis now includes the injected failure type
and configured delay. Treat recommendations as hypotheses, not confirmed causes
or automatic fixes. These prompt refinements were made after the saved live run.
