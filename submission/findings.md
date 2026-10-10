# Team 28: Ranked Findings

Generated from real local execution 20261010T172616441Z. Model: qwen2.5:1.5b.

## AI Experiment Ranking

1. **workshop-delay** (20 sec): Identify the most critical module affected by a single failure. Expected impact: Measure the impact of isolated failures on different modules.
2. **database-crash** (20 sec): Analyze the impact of a network delay on the shared SQL Server dependency. Expected impact: Determine the extent of shared dependency failures.
3. **workshop-crash** (20 sec): Measure the response latency under 500 ms egress delay on the Workshop API. Expected impact: Understand the response latency of the Workshop API.

**Rationale review:** the small model confused crash and network-delay descriptions in some reasons above. They are retained verbatim, not corrected to look stronger. The validated ID and code-owned registry determine the actual mechanism. Natural-language correctness is not guaranteed by schema validation.

## Measurements

| Experiment | Evidence run | Failed fault probes / total | Verified recovery sec | Probe score /100 | Rollback |
| --- | --- | --- | --- | --- | --- |
| workshop-delay | 20261010T172732437Z | 7/21 | 0.37 | 76.6 | Maximum fault duration reached |
| database-crash | 20261010T172848599Z | 2/2 | 16.98 | 25.8 | Safety threshold breached: 2 modules impacted |
| workshop-crash | 20261010T173009668Z | 7/21 | 3.09 | 75.9 | Maximum fault duration reached |
| workshop-crash-with-load | 20261010T174036469Z | 3/9 | 2.5 | 73.8 | Manual kill switch |

Failures include HTTP-200 offline pages. Recovery is measured from completed restoration command to all-page health, not total outage time. Raw JSON and CSV retain individual latencies and timestamps.

| Experiment | Module | Baseline p95 ms | Fault p95 observed ms | Failed / sampled |
| --- | --- | --- | --- | --- |
| workshop-delay | CustomerManagement | 35.9 | 32.9 | 0/7 |
| workshop-delay | VehicleManagement | 18.6 | 21.9 | 0/7 |
| workshop-delay | WorkshopManagement | 28.8 | 2023.1 | 7/7 |
| database-crash | CustomerManagement | 27.6 | 2049.8 | 1/1 |
| database-crash | VehicleManagement | 31.5 | 2029.5 | 1/1 |
| database-crash | WorkshopManagement | 40.3 | not sampled | 0/0 |
| workshop-crash | CustomerManagement | 45.2 | 27.7 | 0/7 |
| workshop-crash | VehicleManagement | 25.3 | 23.7 | 0/7 |
| workshop-crash | WorkshopManagement | 31.2 | 2020.3 | 7/7 |
| workshop-crash-with-load | CustomerManagement | 21.8 | 1517.8 | 0/3 |
| workshop-crash-with-load | VehicleManagement | 55.8 | 102.6 | 0/3 |
| workshop-crash-with-load | WorkshopManagement | 26 | 2146.7 | 3/3 |

Early safety rollback can stop sampling before every module is measured. Missing fault samples are not proof of availability.

## Ranked AI Interpretations

1. **[high] Multiple Availability Failures in 'WorkshopManagement' Module** (workshop-delay): Multiple instances of high latency (2022.5 ms) in the 'WorkshopManagement' module, exceeding the baseline median of 28.8 ms, indicating an availability failure. Recommended fix: Review and optimize the module's performance to reduce latency.. Evidence: 20261010T172732437Z/E1, E2, E3, E4, E5, E6, E7. Model confidence: high.

2. **[high] High Latency and Frequent Availability Failures in 'WorkshopManagement' Module** (workshop-delay): The module is experiencing frequent availability failures, with high latency (2022.5 ms) consistently exceeding the baseline median of 28.8 ms. Recommended fix: Identify and address the root cause of the high latency and frequent failures.. Evidence: 20261010T172732437Z/E1, E2, E3, E4, E5, E6, E7. Model confidence: high.

3. **[high] System instability across modules** (database-crash): Multiple modules experienced high latency and availability failures, indicating potential system instability. Recommended fix: Perform a thorough system health check and investigate potential bottlenecks or configuration issues.. Evidence: 20261010T172848599Z/E1, E2, E3. Model confidence: high.

4. **[high] Recovery process instability** (database-crash): Several modules showed high latency and availability failures during recovery phases, suggesting potential issues with the recovery process. Recommended fix: Review and optimize the recovery process to ensure it does not introduce additional latency or failures.. Evidence: 20261010T172848599Z/E4, E5, E6, E7, E8, E9, E10, E11. Model confidence: high.

5. **[high] Prolonged Availability Failures in 'WorkshopManagement' Module** (workshop-crash): Multiple anomalies in the 'WorkshopManagement' module indicate prolonged availability failures, with latency consistently exceeding the baseline threshold. Recommended fix: Review and optimize the module's performance to reduce latency and improve availability.. Evidence: 20261010T173009668Z/E1, E2, E3, E4, E5, E6, E7. Model confidence: high.

6. **[high] Recovery Event in 'WorkshopManagement' Module** (workshop-crash): A recovery event in the 'WorkshopManagement' module suggests that the system has successfully recovered from an availability failure. Recommended fix: Monitor the module's performance to ensure it can handle failures and recover quickly.. Evidence: 20261010T173009668Z/E8. Model confidence: high.

7. **[medium] Latency Increase During Recovery in 'WorkshopManagement' Module** (workshop-crash): A latency increase in the 'WorkshopManagement' module during recovery indicates that the system is still processing the failure event, which is expected. Recommended fix: Ensure that the module's recovery process is optimized to reduce latency.. Evidence: 20261010T173009668Z/E9. Model confidence: medium.

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

20261010T174030496Z: Workshop crash plus bounded read traffic. See its report and load.json. Autocannon's HTTP-200 counts are not healthy-page counts; page-content probes are authoritative.

## Score Method

Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.

Heuristic for this experiment only; unequal sampling and censored timeouts. Not an AI score, calibrated SLA, write-correctness or durability guarantee.

## Validation And Residual Risks

Fresh Compose project with separate volumes: 20261010T172435409Z. All 13 services running; configured health checks pass; all three pages healthy; customer, vehicle, scheduling and completion workflow passed. Existing garage data was not cleared. Cached rebuilt images were used, not an uncached rebuild.

Legacy application transitive NuGet dependencies emit high-severity vulnerability warnings. Sandbox demonstration only, not production readiness. Remaining work: durability/write-fault tests, repeated controlled trials, targeted legacy dependency upgrades and model-evaluation coverage. Dashboard npm audit is clean after a scoped UUID override.
