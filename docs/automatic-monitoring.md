# Automatic Failure Monitoring

Start the dashboard from the repository root:

```powershell
cd .\dashboard
npm.cmd start
```

Open the printed localhost URL and select **Failure monitor**. Monitoring starts with
the dashboard server, even with no browser open and no experiment running. The
server must stay running. The browser's Live updates checkbox only pauses display
refresh; it does not stop monitoring.

## Detection

- Checks the Customer, Vehicle and Workshop pages, plus this checkout's Compose
  container inventory, approximately every 5 seconds. Slow probes can extend this.
- HTTP errors, connection failures, timeouts, unexpected pages and HTTP-200 offline
  fallbacks count as failed page probes.
- Two consecutive failed observations open an incident. Two consecutive healthy
  observations verify recovery. One transient failure is not a confirmed incident.
- After six healthy samples, detects latency above the maximum of 500 ms, three
  times the healthy median, or median plus 250 ms. The rolling baseline retains
  60 samples per module, excluding failed/slow probes and active experiments.
- Detects stopped, unhealthy or missing core containers. Docker inventory errors
  remain an observability warning, not proof that a container has failed.
- Records failure/recovery changes, observed duration, recent evidence, probable
  dependency relationships, investigation steps and suggested fixes.
- Experiment/agent activity is recorded as context, not proof that an experiment
  caused the incident. Background services are observed by container state only.

## AI And Evidence

The detector is deterministic and independent of AI availability. When local
Ollama has `qwen2.5:1.5b`, it adds a beginner-friendly explanation, possible cause
and suggested solutions to queued incidents, including recovered ones. Only one bounded 45-second
AI request runs at a time; new requests are not started during agent activity.
The detector supplies the observed symptom summary. AI selects a possible cause
and useful fixes from evidence-grounded, bounded candidates rather than inventing
measurements or configuration. Structured responses and candidate membership are
validated; model output never becomes a command.
AI failures retain the evidence-based diagnosis. Set `MONITOR_AI=0` before
starting the dashboard to disable these optional explanations.

History is saved under `agent/monitor/incidents.json` (ignored by Git). Download
the current snapshot with the download icon in the Failure monitor. Restarting
the server retains history; unresolved incidents await fresh verification. The
healthy baseline and short latency trace relearn after restart.

## Demonstration

1. Start the app and dashboard; wait for at least six healthy monitoring samples.
2. Use the existing dashboard to execute a bounded Workshop crash in your sandbox.
3. Open Failure monitor: observe the page outage and container-health incident,
   evidence-based explanation, experiment context and recommended investigation.
4. Let the existing watchdog restore the service, or use Emergency stop. Observe
   two healthy samples followed by Recovery verified in Detected changes.
5. Download the incident snapshot. A short outage may end before confirmation;
   keep the original experiment evidence for finer-grained measurements.

This monitor **does not cause failures or automatically apply fixes**. It detects
observable symptoms, not every failure. Read pages and container state cannot
prove event delivery, write durability, data loss or an exact root cause. Confirm
causes using application logs/traces and verify full workflows after a fix.
Monitoring AI runs on the same machine and may affect latency. Reports generated
for the earlier submission remain historical evidence; this change does not
silently replace or regenerate them.
