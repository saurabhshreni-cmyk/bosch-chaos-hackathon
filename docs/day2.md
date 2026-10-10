# Day-2 Completion And Reproduction

Only run faults in your own local sandbox. Keep the existing garage volumes.
Install dashboard dependencies and the local model using the README first.

## AI Ranking And Three Experiments

From the repository root:

```powershell
./agent/run-agent.ps1 -Execute -MaxExperiments 3 -BaselineSeconds 180
```

The AI ranks the allowed catalog using the dependency map and healthy baseline.
The controller validates complete, unique rankings, fixed targets, durations,
reasons and permitted fields. The model cannot generate executable commands.
Each experiment is analyzed only after restoration and verification. An
unhealthy baseline, failed recovery, invalid plan or failed AI analysis aborts
the remaining budget. Use `-RuleBased` explicitly for orchestration without AI.

The final retained run is indexed by `submission/manifest.json`. Raw JSON and
CSV are in `docs/evidence/day2/<id>/`. A prior three-minute steady baseline is
retained in `docs/evidence/day1/`; the final suite uses a shorter confirmation
baseline. Do not call that shorter sample a three-minute test.

The small model can confuse experiment descriptions in its reasons. Review
them against the actual catalog mechanism. Schema validation makes execution
bounded; it does not establish the correctness of natural-language rationale.

## Optional Combined Failure

```powershell
./agent/run-agent.ps1 -Execute -RuleBased -MaxExperiments 1 -BaselineSeconds 30 -ExperimentIds workshop-crash-with-load
```

The fixed tool kills only the Workshop API and starts autocannon with two
connections and at most ten read requests per second for at most 30 seconds.
No writes, arbitrary URLs or unbounded traffic are allowed. STOP cancels the
load and requests service restoration. The load worker has its own duration
limit, separate from the service restoration watchdog. An HTTP-200 offline
fallback is a failure in the content-aware probes, even if autocannon counts
its HTTP response as successful. `load.json` retains the traffic profile and
metrics. This stretch run uses fixed order; it is not presented as an AI run.

## Fix And Retest

The web app now sets a two-second API request budget and makes one attempt,
with the existing fallback policy. Unconditional retries could repeat a
non-idempotent command after an ambiguous failure. Focused console tests cover
healthy results, timeout fallback and a single failed write attempt.

Matched before/after Workshop 500 ms network-delay experiments and their
comparison are retained. Faster offline fallback improves responsiveness but
does not restore availability. Sampling counts, early rollback and failures
are disclosed. No statistically established causal improvement is claimed.

## Clean Startup

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/validate-clean-start.ps1
```

Uses freshly named volumes, networks and containers in a separate local
Compose project. Checks all running services and configured health checks,
then uses Edge to create a synthetic customer and vehicle, plan maintenance
and complete it. Only that newly created project is removed afterward. The
original garage is never cleared. Rebuilt cached images are used. Generated
resolved Compose files are ignored; only sanitized result evidence is packaged.

## Final Deliverables

`submission/README.md` lists the five deliverables, checks and remaining human
submission steps. The captioned video contains a live combined fault and STOP
recovery plus ranking/findings from a completed real model run. The distinction
is shown in captions. Architecture PDF is one page. AI recommendations remain
hypotheses requiring human review; measured anomalies are independent of AI.

Legacy transitive .NET dependencies still generate high-severity NuGet warnings.
This is a local hackathon sandbox, not a production-security certification.
Do not describe the heuristic read-probe score as an AI score or calibrated SLA.
