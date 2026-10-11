# Automatic discovery and controlled testing

Enable **Automatic discovery** in the dashboard, choose the experiments you permit, then preview or explicitly confirm execution. The discovery worker examines the current baseline, recent monitor incidents (last 24 hours, at most 20 inputs), and the dependency map. It separates observed failures, observed slowdowns, historical incidents and possible shared-dependency risks.

```powershell
./agent/run-agent.ps1 -AutoDiscover
./agent/run-agent.ps1 -AutoDiscover -Execute -MaxExperiments 3
./agent/run-agent.ps1 -AutoDiscover -Execute -MaxExperiments 1 -ExperimentIds workshop-delay-high
```

The AI planner receives this discovery evidence and ranks only the allowed catalog. In explicit no-model mode, discovery priorities determine catalog order. After each injected experiment, the detection and recommendation workers measure impact and suggest fixes. All run artifacts and discovery results are displayed in the dashboard.

**An existing outage is not an invitation to inject another fault.** Discovery records an unhealthy baseline, then the coordinator refuses injection. Restore health and start a new session. Experiments reveal vulnerabilities; they do not repair them.

Runnable tools cover Workshop crash, SQL outage, RabbitMQ outage, 500 ms Workshop delay, bounded crash plus read traffic, and the new stronger 1000 ms delay scenario (10 seconds by default, 20 maximum). Both delay scenarios are the same failure category, not two distinct failure types.

Packet loss, database contention and disk exhaustion are proposed scenarios only. They remain non-executable until a bounded implementation, rollback and tests are added. The model cannot invent shell commands, new targets or runnable tools. No host disk filling, database data deletion, production targets or automatically applied recommendations are permitted.

The agent runs one finite, explicitly authorized session, not an unattended infinite attack loop. STOP, checkout ownership, fresh preflight, bounded duration and recovery checks are unchanged. Read probes cannot discover every possible fault or prove root cause, write correctness or message durability.

## Stretch goals and submission

- Live dashboard: stages, worker status, measurements, incidents, recommendations and 3D dependencies.
- Combined failures: `workshop-crash-with-load` overlaps an API outage with two connections and 10 local GETs/second; no writes.
- Fix and retest: `submission/comparison.json` and `submission/findings.md` retain matched before/after evidence for the two-second request budget and removal of unconditional write retries. Fallback became faster, but availability worsened under delay. Do not claim universal improvement.
- Five local deliverables: repository README, captioned demo under three minutes, architecture PDF, ranked findings, and team details, linked from `submission/README.md`.
- Repository publishing and portal upload are separate steps. Local implementation and files do not imply that the latest changes have been pushed or submitted.
# Catalog-Free Detection

The dashboard provides both paths together. **Detect failures** collects a
read-only detection session without a catalog. **Preview plan** and **Run
experiments**, with **Detection-informed planning** enabled, collect observations
first and use them to prioritize the checked registered tests. Run experiments
requires explicit sandbox confirmation and a healthy baseline. The independent
Failure monitor remains active in all modes. Detection does not automatically
authorize injection or turn hypothetical risks into proven failures.

To find current failures without selecting any predefined experiment:

```powershell
./agent/run-agent.ps1 -DetectOnly -BaselineSeconds 30
```

This mode does not load the experiment catalog, require an AI model, select a
plan or inject a fault. It saves measured failures, historical incidents and
potential dependency risks in `discovery.json` and `findings.md`. An unhealthy
application is a detection result, not a reason to abort this read-only mode.
`-DetectOnly -Execute` is rejected. Select its session in the dashboard's planning
view to see the read-only results. The Failure monitor independently probes the
application continuously and supplies incident explanations and suggested fixes.

Detection is independent of the injection catalog, but it is not omniscient:
page probes cannot discover every internal defect or establish root cause.
Controlled injection still requires bounded, registered tools; generating
arbitrary destructive commands is not necessary for automatic detection.

