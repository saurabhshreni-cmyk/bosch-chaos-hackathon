# Database Kill and AI Observability

## Run

From the repository root, with the application already working:

```powershell
./chaos-scripts/kill-database.ps1
```

The wrapper uses the same runner as the Workshop experiment, targeting only
the `sqlserver` Compose service. It collects healthy baseline reads, sends
`docker kill` to the resolved container, probes the three module pages, and
starts the same container again. The SQL data volume is not deleted or recreated.

Defaults: 30-second maximum outage, three baseline rounds, five-second request
timeout, rollback once two distinct modules have failed, and up to 120 seconds
of recovery checking. Failures in two modules are enough to stop early because
SQL Server is a shared dependency. Setting `-MaxImpactedModules 3` allows the
runner to observe three failing modules before rollback, subject to the deadline.

The `chaos-scripts/STOP` file works for both experiments. Only one runner can
hold the experiment lock in this checkout at a time. This lock does not coordinate
separate clones or machines. See [Workshop safety controls](kill-service.md)
for the manual switch and watchdog limitations.

After a forced PowerShell termination, restore from the repository root:

```powershell
docker compose -f src/docker-compose.yml start sqlserver
```

## Measurements and Anomaly Detection

Each run saves these local artifacts under `chaos-scripts/results/<run-id>/`:

- `report.json`: target, rollback, recovery timing, and request measurements.
- `samples.csv`: timestamped request measurements.
- `anomalies.json`: per-module baseline statistics, evidence IDs, anomaly types,
  severity, and separate AI status and interpretations.

Analysis also runs on saved evidence if the experiment reports failed recovery.
If setup fails before a report exists, no analysis is possible. Generated files
are ignored by Git; retain selected evidence separately for submission.

The deterministic detector flags failed requests and offline fallback pages,
including fallbacks with HTTP 200. For healthy requests, it flags latency above
the maximum of three thresholds: baseline median plus 250 ms, three times the
median, or median plus six robust standard deviations estimated from MAD.
The additive floor prevents a tiny baseline from flagging normal jitter.

These checks are statistics and rules, **not a trained AI model**. Three baseline
samples are too few for strong statistical conclusions. Requests are sequential,
and timed-out latencies are lower bounds. These read probes do not establish
write correctness, data durability, message loss, or the health of background jobs.

## Optional AI Integration

Without `-Model`, analysis works offline and explicitly records
`AiStatus: Not configured`. To install the optional Docker-hosted model:

```powershell
./agent/setup-ai.ps1
docker compose -f agent/compose.ai.yml exec -T ollama ollama list
./chaos-scripts/kill-database.ps1 -Model qwen2.5:1.5b
```

To analyze an existing report without injecting another fault:

```powershell
./chaos-scripts/analyze-anomalies.ps1 -ReportPath ./chaos-scripts/results/RUN_ID/report.json
./chaos-scripts/analyze-anomalies.ps1 -ReportPath ./chaos-scripts/results/RUN_ID/report.json -Model qwen2.5:1.5b
```

The integration calls local [Ollama's chat endpoint](https://docs.ollama.com/api/chat)
with streaming disabled and JSON output. It sends aggregated measurements and
anomaly evidence, not raw exception text, customer records, or Docker credentials.
The model is asked to rank findings, explain anomalies, recommend fixes, and cite
evidence IDs. Returned findings must include required fields and existing evidence
references. Format validation does not prove that interpretations are correct;
review them before submission. The model cannot execute commands or change safety
limits. A failed model request retains measured anomalies and records the failure.

No model installation or download is performed by these scripts. Local inference
can consume CPU and memory, so it runs after the experiment has restored services.
The AI request has a 180-second timeout for CPU inference. Anomaly analysis overwrites `anomalies.json`
in that run folder; preserve earlier versions if comparing model outputs.

## Verified Local Run

On October 10, 2026, run `20261010T085007976Z` recorded:

- All three module baseline pages healthy.
- Customer and Vehicle timed out at approximately five seconds during the fault.
- The two-module safety threshold caused early restoration.
- Initial recovery probes still failed, including a Vehicle fallback with HTTP 200.
- A later recovery round found all three modules healthy.
- Five anomalous samples detected; no AI model configured.

This demonstrates shared-dependency impact and page recovery. It does not prove
that every API process or background worker recovered, or that no data was lost.
