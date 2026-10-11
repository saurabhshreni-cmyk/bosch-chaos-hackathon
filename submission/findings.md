# Team 28: Ranked Findings

Generated from real local execution 20261010T215606032Z. Model: qwen2.5:1.5b.

## AI Experiment Ranking

1. **workshop-crash** (20 sec): Identify the root cause of the crash by isolating the failure and observing its effects on other services. Expected impact: Measure the impact of isolated failures on the system.
2. **database-crash** (20 sec): Understand the response time of the system under varying network conditions to optimize performance. Expected impact: Measure the impact of network latency on the system.
3. **workshop-delay** (20 sec): Identify the dependencies that cause the outage and assess the impact on the system. Expected impact: Measure the impact of shared dependency outages on the system.

**Rationale review:** the small model confused crash and network-delay descriptions in some reasons above. They are retained verbatim, not corrected to look stronger. The validated ID and code-owned registry determine the actual mechanism. Natural-language correctness is not guaranteed by schema validation.

## Measurements

| Experiment | Evidence run | Failed fault probes / total | Verified recovery sec | Probe score /100 | Rollback |
| --- | --- | --- | --- | --- | --- |
| workshop-crash | 20261010T215952061Z | 7/21 | 0.74 | 76.5 | Maximum fault duration reached |
| database-crash | 20261010T220113314Z | 2/2 | 30.29 | 22.4 | Safety threshold breached: 2 modules impacted |
| workshop-delay | 20261010T220315060Z | 5/18 | 1.07 | 79.2 | Maximum fault duration reached |
| workshop-crash-with-load | 20261010T222309536Z | 3/9 | 4.55 | 75.5 | Manual kill switch |

Failures include HTTP-200 offline pages. Recovery is measured from completed restoration command to all-page health, not total outage time. Raw JSON and CSV retain individual latencies and timestamps.

| Experiment | Module | Baseline p95 ms | Fault p95 observed ms | Failed / sampled |
| --- | --- | --- | --- | --- |
| workshop-crash | CustomerManagement | 73.6 | 86.1 | 0/7 |
| workshop-crash | VehicleManagement | 19.1 | 22.7 | 0/7 |
| workshop-crash | WorkshopManagement | 32 | 2030.7 | 7/7 |
| database-crash | CustomerManagement | 114.9 | 2247.6 | 1/1 |
| database-crash | VehicleManagement | 349.1 | 2162.1 | 1/1 |
| database-crash | WorkshopManagement | 243.5 | not sampled | 0/0 |
| workshop-delay | CustomerManagement | 165.5 | 445.1 | 0/6 |
| workshop-delay | VehicleManagement | 77.1 | 112.4 | 0/6 |
| workshop-delay | WorkshopManagement | 120.7 | 2432.4 | 5/6 |
| workshop-crash-with-load | CustomerManagement | 63.4 | 24.2 | 0/3 |
| workshop-crash-with-load | VehicleManagement | 21.2 | 23.1 | 0/3 |
| workshop-crash-with-load | WorkshopManagement | 26.2 | 2022.3 | 3/3 |

Early safety rollback can stop sampling before every module is measured. Missing fault samples are not proof of availability.

## Ranked AI Interpretations

1. **[high] High Latency and Availability Failures in 'WorkshopManagement' Module** (workshop-crash): Multiple anomalies in the 'WorkshopManagement' module indicate high latency and availability failures. The latency consistently exceeds the baseline threshold, suggesting potential issues with the module's performance or infrastructure. Recommended fix: Review and optimize the module's performance, possibly addressing infrastructure or code issues.. Evidence: 20261010T215952061Z/E1, E2, E3, E4, E5, E6, E7. Model confidence: high.

2. **[high] System instability across modules** (database-crash): Multiple modules experienced high latency and availability failures, indicating potential system instability. Recommended fix: Perform a thorough system health check and investigate potential bottlenecks.. Evidence: 20261010T220113314Z/E1, E2, E3. Model confidence: high.

3. **[high] Multiple anomalies in 'WorkshopManagement' module** (workshop-delay): Multiple anomalies in the 'WorkshopManagement' module indicate prolonged latency and availability failures, with some reaching high severity levels. Recommended fix: Review and optimize the module's performance and availability mechanisms.. Evidence: 20261010T220315060Z/E1, E2, E3, E4, E5, E6, E7. Model confidence: high.

4. **[high] Anomalies in 'WorkshopManagement' module** (workshop-delay): Anomalies in the 'WorkshopManagement' module suggest prolonged latency and availability failures, with some reaching high severity levels. Recommended fix: Review and optimize the module's performance and availability mechanisms.. Evidence: 20261010T220315060Z/E1, E2, E3, E4, E5, E6, E7. Model confidence: high.

5. **[medium] Latency Increase in 'WorkshopManagement' Module** (workshop-crash): A recovery event in the 'WorkshopManagement' module indicates that the latency has increased but the module is now available again. This suggests that the issue was likely resolved, but it's still important to monitor the module's performance to prevent future failures. Recommended fix: Monitor the module's performance closely to ensure it remains stable and efficient.. Evidence: 20261010T215952061Z/E8. Model confidence: medium.

6. **[medium] Latency increase in modules** (database-crash): Several modules showed latency increases, which could indicate performance degradation or resource contention. Recommended fix: Monitor the affected modules for further latency spikes and optimize resource usage.. Evidence: 20261010T220113314Z/E4, E5, E6, E7, E8, E9, E10. Model confidence: medium.

AI statements above are interpretations, not established root causes. A crash is deliberately injected; the finding is the observed propagation, fallback or recovery behavior. Read probes cannot establish data loss, writes or durable event delivery.

## Applied Fix And Retest

Two-second API request budgets and single-attempt fallback replace unconditional retries, including retries of potentially non-idempotent commands. Focused tests verify healthy results, timeout fallback and one write attempt.

| Module | Before p95 observed ms | After p95 observed ms | Before failures / probes | After failures / probes |
| --- | --- | --- | --- | --- |
| CustomerManagement | 5044.1 | 165.1 | 0/4 | 0/7 |
| VehicleManagement | 22.7 | 112.9 | 0/3 | 0/7 |
| WorkshopManagement | 4555.2 | 2064.3 | 0/3 | 7/7 |

One matched before/after pair, not a causal statistical study. Timeout durations are lower bounds. Compare responsiveness, failure rate and sampling counts together; faster fallback is not restored availability.

Workshop deliberately fails fast under delay. This is a responsiveness improvement with an availability tradeoff, not proof that all resilience dimensions improved. Early rollback and unequal probe counts are reported, not hidden. Matched run IDs: 20261010T171223563Z → 20261010T172516238Z.

## Combined Failure

20261010T222301763Z: Workshop crash plus bounded read traffic. See its report and load.json. Autocannon's HTTP-200 counts are not healthy-page counts; page-content probes are authoritative.

## Score Method

Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.

Heuristic for this experiment only; unequal sampling and censored timeouts. Not an AI score, calibrated SLA, write-correctness or durability guarantee.

## Validation And Residual Risks

Fresh Compose project with separate volumes: 20261010T172435409Z. All 13 services running; configured health checks pass; all three pages healthy; customer, vehicle, scheduling and completion workflow passed. Existing garage data was not cleared. Cached rebuilt images were used, not an uncached rebuild.

Legacy application transitive NuGet dependencies emit high-severity vulnerability warnings. Sandbox demonstration only, not production readiness. Remaining work: durability/write-fault tests, repeated controlled trials, targeted legacy dependency upgrades and model-evaluation coverage. Dashboard npm audit is clean after a scoped UUID override.
