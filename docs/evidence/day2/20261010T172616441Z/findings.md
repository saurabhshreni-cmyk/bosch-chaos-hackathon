# Chaos Agent Findings

Run: 20261010T172616441Z. Mode: AI: qwen2.5:1.5b. Execute: True.

Error:

## workshop-delay

Recovered: True. Recovery: 0.37 s. Anomalies: 7. Rollback: Maximum fault duration reached.

Evidence run: 20261010T172732437Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 76.6/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## database-crash

Recovered: True. Recovery: 16.98 s. Anomalies: 11. Rollback: Safety threshold breached: 2 modules impacted.

Evidence run: 20261010T172848599Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 25.8/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## workshop-crash

Recovered: True. Recovery: 3.09 s. Anomalies: 9. Rollback: Maximum fault duration reached.

Evidence run: 20261010T173009668Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 75.9/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## Ranked AI Findings

- [high] System instability across modules (database-crash): Multiple modules experienced high latency and availability failures, indicating potential system instability. Fix: Perform a thorough system health check and investigate potential bottlenecks or configuration issues.. Evidence: 20261010T172848599Z/E1, E2, E3. Confidence: high.
- [high] Recovery Event in 'WorkshopManagement' Module (workshop-crash): A recovery event in the 'WorkshopManagement' module suggests that the system has successfully recovered from an availability failure. Fix: Monitor the module's performance to ensure it can handle failures and recover quickly.. Evidence: 20261010T173009668Z/E8. Confidence: high.
- [high] Prolonged Availability Failures in 'WorkshopManagement' Module (workshop-crash): Multiple anomalies in the 'WorkshopManagement' module indicate prolonged availability failures, with latency consistently exceeding the baseline threshold. Fix: Review and optimize the module's performance to reduce latency and improve availability.. Evidence: 20261010T173009668Z/E1, E2, E3, E4, E5, E6, E7. Confidence: high.
- [high] High Latency and Frequent Availability Failures in 'WorkshopManagement' Module (workshop-delay): The module is experiencing frequent availability failures, with high latency (2022.5 ms) consistently exceeding the baseline median of 28.8 ms. Fix: Identify and address the root cause of the high latency and frequent failures.. Evidence: 20261010T172732437Z/E1, E2, E3, E4, E5, E6, E7. Confidence: high.
- [high] Multiple Availability Failures in 'WorkshopManagement' Module (workshop-delay): Multiple instances of high latency (2022.5 ms) in the 'WorkshopManagement' module, exceeding the baseline median of 28.8 ms, indicating an availability failure. Fix: Review and optimize the module's performance to reduce latency.. Evidence: 20261010T172732437Z/E1, E2, E3, E4, E5, E6, E7. Confidence: high.
- [high] Recovery process instability (database-crash): Several modules showed high latency and availability failures during recovery phases, suggesting potential issues with the recovery process. Fix: Review and optimize the recovery process to ensure it does not introduce additional latency or failures.. Evidence: 20261010T172848599Z/E4, E5, E6, E7, E8, E9, E10, E11. Confidence: high.
- [medium] Latency Increase During Recovery in 'WorkshopManagement' Module (workshop-crash): A latency increase in the 'WorkshopManagement' module during recovery indicates that the system is still processing the failure event, which is expected. Fix: Ensure that the module's recovery process is optimized to reduce latency.. Evidence: 20261010T173009668Z/E9. Confidence: medium.

Read probes do not prove write correctness or message durability. ProbeScore is a transparent heuristic, not AI-generated or a calibrated SLA. Review AI interpretations against evidence.
