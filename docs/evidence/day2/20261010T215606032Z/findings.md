# Chaos Agent Findings

Run: 20261010T215606032Z. Mode: AI: qwen2.5:1.5b. Execute: True.

Error:

## workshop-crash

Recovered: True. Recovery: 0.74 s. Anomalies: 8. Rollback: Maximum fault duration reached.

Evidence run: 20261010T215952061Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 76.5/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## database-crash

Recovered: True. Recovery: 30.29 s. Anomalies: 13. Rollback: Safety threshold breached: 2 modules impacted.

Evidence run: 20261010T220113314Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 22.4/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## workshop-delay

Recovered: True. Recovery: 1.07 s. Anomalies: 7. Rollback: Maximum fault duration reached.

Evidence run: 20261010T220315060Z. AI status: Completed; interpretations require human review.
Read-probe heuristic score: 79.2/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.


## Ranked AI Findings

- [high] Anomalies in 'WorkshopManagement' module (workshop-delay): Anomalies in the 'WorkshopManagement' module suggest prolonged latency and availability failures, with some reaching high severity levels. Fix: Review and optimize the module's performance and availability mechanisms.. Evidence: 20261010T220315060Z/E1, E2, E3, E4, E5, E6, E7. Confidence: high.
- [high] Multiple anomalies in 'WorkshopManagement' module (workshop-delay): Multiple anomalies in the 'WorkshopManagement' module indicate prolonged latency and availability failures, with some reaching high severity levels. Fix: Review and optimize the module's performance and availability mechanisms.. Evidence: 20261010T220315060Z/E1, E2, E3, E4, E5, E6, E7. Confidence: high.
- [high] System instability across modules (database-crash): Multiple modules experienced high latency and availability failures, indicating potential system instability. Fix: Perform a thorough system health check and investigate potential bottlenecks.. Evidence: 20261010T220113314Z/E1, E2, E3. Confidence: high.
- [high] High Latency and Availability Failures in 'WorkshopManagement' Module (workshop-crash): Multiple anomalies in the 'WorkshopManagement' module indicate high latency and availability failures. The latency consistently exceeds the baseline threshold, suggesting potential issues with the module's performance or infrastructure. Fix: Review and optimize the module's performance, possibly addressing infrastructure or code issues.. Evidence: 20261010T215952061Z/E1, E2, E3, E4, E5, E6, E7. Confidence: high.
- [medium] Latency increase in modules (database-crash): Several modules showed latency increases, which could indicate performance degradation or resource contention. Fix: Monitor the affected modules for further latency spikes and optimize resource usage.. Evidence: 20261010T220113314Z/E4, E5, E6, E7, E8, E9, E10. Confidence: medium.
- [medium] Latency Increase in 'WorkshopManagement' Module (workshop-crash): A recovery event in the 'WorkshopManagement' module indicates that the latency has increased but the module is now available again. This suggests that the issue was likely resolved, but it's still important to monitor the module's performance to prevent future failures. Fix: Monitor the module's performance closely to ensure it remains stable and efficient.. Evidence: 20261010T215952061Z/E8. Confidence: medium.

Read probes do not prove write correctness or message durability. ProbeScore is a transparent heuristic, not AI-generated or a calibrated SLA. Review AI interpretations against evidence.
