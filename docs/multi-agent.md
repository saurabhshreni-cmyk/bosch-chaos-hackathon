# Multi-agent execution

The existing `agent/run-agent.ps1` commands now use isolated PowerShell role workers. The coordinator owns the session lock, healthy baseline gate, plan validation, experiment budget and stop decisions. Each worker has its own process and request/response/log artifacts under `agent/runs/<session>/workers/`.

| Role | Input | Output | Execution permission |
| --- | --- | --- | --- |
| Discovery | Current baseline, incident history, dependency map | Observed weaknesses, potential risks and safe candidates | Read and analyze evidence |
| Planner | Dependency map, baseline, allowed catalog | Ranked validated experiments | Local model inference only |
| Injection | Validated plan | Fault report and recovery evidence | Registered sandbox tools only |
| Detection | Fault report | `detection.json` with measured anomalies | Read and analyze evidence |
| Recommendation | Detector evidence and fault report | `anomalies.json` with evidence-linked findings | Local model inference only |
| Live detector | Page and container probes | Incidents and recovery transitions | Read-only dashboard monitoring |

Only the planner and recommendation roles use an LLM. Detection and injection are deterministic tools, not additional AI models. Role separation improves isolation and traceability; it does not promise faster inference on one CPU/model. Faults and model calls remain serialized. The dashboard's continuous detector runs during worker execution, but its optional model analysis is deferred while an experiment/session is active.

```powershell
# Healthy baseline and AI planning only: no failure injection.
./agent/run-agent.ps1

# Explicitly execute up to three experiments, one at a time.
./agent/run-agent.ps1 -Execute -MaxExperiments 3

# No-model planning preview.
./agent/run-agent.ps1 -RuleBased -BaselineSeconds 10 -MaxExperiments 1
```

The dashboard Overview shows role status, PID and errors for new sessions. Older evidence without worker metadata remains readable. The existing STOP file, independent rollback watchdog, target allowlist, duration bounds and recovery gate are retained. Never terminate an injection worker manually: use the existing kill switch so its restoration path can complete. Recommendations are hypotheses for review, not automatically applied fixes.

Worker request files are internal coordinator artifacts, not a public command API or an OS security boundary. Do not feed them untrusted third-party plans. All worker-side targets are resolved through the local registry; no model-generated shell commands are executed.
