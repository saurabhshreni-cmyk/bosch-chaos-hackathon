# Pitstop Chaos Dashboard

The dashboard is a separate local console for the existing PowerShell chaos
agent. It does not replace Pitstop's garage UI or simulate experiment results.

## Start

Install Node.js 22 or newer with npm. Keep the Pitstop Docker Compose application
running, then from the repository root:

```powershell
cd dashboard
npm install
npm start
```

The server binds only to `127.0.0.1`, normally port 7010. If occupied, it tries
7011 through 7020 and prints the selected URL. Keep the terminal running.

For a display-only console with every command disabled:

```powershell
$env:DASHBOARD_READ_ONLY = '1'
npm start
```

Remove that environment variable before starting an interactive console again.

## Demo

1. Open the dashboard and select a completed session in the history. Overview
   shows plans, fault measurements, rollback reasons, and verified recovery.
2. Open Dependencies for the application's service and data-flow map. Open
   Evidence & findings for baseline statistics, measured anomalies, and AI
   findings with evidence references. Download the evidence JSON or findings.
3. Select Fixed order, one experiment, budget 1, and a short baseline such as
   10 seconds. Click Preview plan. Watch baseline samples, lifecycle events,
   and the activity log appear. This injects no faults. A short demo baseline
   is not a substitute for the longer Day-1 steady baseline.
4. To demonstrate local AI planning, select Local AI and an installed model.
   Ollama must be running on `localhost:11434`; use `agent/setup-ai.ps1` if
   needed. Fixed order is explicitly not AI.
5. For a failure demo, keep Workshop open at `http://localhost:7005/WorkshopManagement`.
   Choose only Workshop crash and budget 1, click Run experiments, and confirm
   this is your team's disposable local sandbox. Watch injection, degradation,
   restoration, verification, and analysis. Only run this after saving local data.
6. Emergency stop creates `chaos-scripts/STOP`. The runner restores the target
   between bounded probes and abandons remaining experiments. Clear STOP only
   after the agent and experiment have finished. Verify the module pages again.

## Data And Limitations

- Session history comes from `agent/runs/*/session.json`. A selected retained
  AI example in `docs/evidence/ai-live` also works on a fresh checkout.
- Existing runs keep their original evidence. They do not gain an invented
  timestamped lifecycle. New runs publish `live-baseline.json`,
  `live-experiment.json`, and session events for live display.
- Live page health probes are current read requests with a two-second timeout.
  The latency chart is the selected session's recorded evidence, not those
  current health requests. Timestamps distinguish the two.
- Docker container health and user-facing page health are separate signals.
  A missing Docker executable or unavailable daemon appears as unknown, not
  healthy. Existing images may contain outdated healthchecks even when pages
  respond; rebuilding and validating those images is separate work.
- AI predictions and recommended fixes are interpretations, not proven root
  causes. Anomaly counts are statistical results. No fabricated resilience
  score is displayed. Read probes cannot prove writes or message durability.
- The dashboard polls every two seconds. An in-flight model request or probe
  may finish before STOP is noticed; emergency stop is not an immediate hard
  process kill. Existing duration watchdogs and rollback controls remain intact.

## Safety And Tests

Commands are limited to registered experiments, fixed local scripts, bounded
baseline durations, and budgets of 1-4. Arbitrary shell commands and untrusted
report paths are not accepted. The server checks Host, same-origin requests,
and a per-process command token; execution requires explicit confirmation.
Shared agent and experiment locks prevent concurrent faults. Do not expose
this local, unauthenticated console through a tunnel or shared network.

```powershell
cd dashboard
npm test
npm run test:browser
```

With the application running, opt in to a real ten-second preview test:

```powershell
$env:RUN_AGENT_TEST = '1'
npm run test:browser
```

This additional test creates a fixed-order plan and live baseline evidence but
does not inject a fault. It is skipped unless explicitly enabled.

Browser checks use installed Microsoft Edge and inspect desktop/mobile views,
rendered assets and charts, evidence, and confirmation controls. They never
confirm a destructive run. Runtime logs and browser artifacts are ignored by Git.
