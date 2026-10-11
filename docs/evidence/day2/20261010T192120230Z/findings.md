# Chaos Agent Findings

Run: 20261010T192120230Z. Mode: AI: qwen2.5:1.5b. Execute: True.

Error:

## workshop-crash

Recovered: True. Recovery: 2.93 s. Anomalies: 9. Rollback: Maximum fault duration reached.

Evidence run: 20261010T192503110Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 75.9/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## database-crash

Recovered: True. Recovery: 20.79 s. Anomalies: 10. Rollback: Safety threshold breached: 2 modules impacted.

Evidence run: 20261010T192632965Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 24.8/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## workshop-delay

Recovered: True. Recovery: 0.53 s. Anomalies: 6. Rollback: Maximum fault duration reached.

Evidence run: 20261010T192804196Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 76.5/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## Ranked AI Findings

- [high] Module Latency and Availability Failures (database-crash): Multiple modules experienced high latency and availability failures, exceeding the baseline thresholds. Fix: Review and optimize the modules' performance and reliability.. Evidence: 20261010T192632965Z/E1, E2, E3. Confidence: high.
- [high] Systemic Availability Failures in 'WorkshopManagement' Module (workshop-delay): The anomalies are consistent across multiple timestamps and modules, indicating a systemic issue. Fix: Review and optimize the module's performance to reduce latency and improve availability.. Evidence: 20261010T192804196Z/E1, E2, E3, E4, E5, E6. Confidence: high.
- [high] Multiple Availability Failures in 'WorkshopManagement' Module (workshop-delay): Multiple anomalies in the 'WorkshopManagement' module with high severity and latency exceeding the baseline median and threshold. Fix: Review and optimize the module's performance to reduce latency and improve availability.. Evidence: 20261010T192804196Z/E1, E2, E3, E4, E5, E6. Confidence: high.
- [high] Module Recovery Failures (database-crash): Several modules showed high latency and availability failures during recovery phases, indicating potential issues with their recovery processes. Fix: Review and optimize the modules' recovery processes.. Evidence: 20261010T192632965Z/E4, E5, E6, E7, E8, E9, E10. Confidence: high.
- [high] Recovery from Availability Failure with High Latency (workshop-crash): A 'recovery' event in the 'WorkshopManagement' module indicates that the system has recovered from an availability failure, but the latency is still above the baseline threshold. Fix: Ensure that the system's recovery process does not introduce additional latency.. Evidence: 20261010T192503110Z/E8. Confidence: high.
- [high] High Latency and Availability Failures in 'WorkshopManagement' Module (workshop-crash): Multiple anomalies in the 'WorkshopManagement' module indicate high latency and availability failures, with some showing recovery but still exceeding the baseline threshold. Fix: Review and optimize the module's performance, possibly by reducing database queries or improving network latency.. Evidence: 20261010T192503110Z/E1, E2, E3, E4, E5, E6, E7. Confidence: high.
- [medium] Latency Increase with High Availability (workshop-crash): A 'Latency increase' event in the 'WorkshopManagement' module shows that the system's latency has increased, but the availability is still above the baseline threshold. Fix: Analyze the system's network or database performance to identify potential bottlenecks.. Evidence: 20261010T192503110Z/E9. Confidence: medium.

Read probes do not prove write correctness or message durability. ProbeScore is a transparent heuristic, not AI-generated or a calibrated SLA. Review AI interpretations against evidence.
