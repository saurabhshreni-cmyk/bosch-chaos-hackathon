# Chaos Agent Findings

Run: 20261010T222301763Z. Mode: Rule-based; no AI used. Execute: True.

Error:

## workshop-crash-with-load

Recovered: True. Recovery: 4.55 s. Anomalies: 4. Rollback: Manual kill switch.

Evidence run: 20261010T222309536Z. AI status: Not configured.
Read-probe heuristic score: 75.5/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.

Measured anomalies only. No AI findings were generated.

Read probes do not prove write correctness or message durability. ProbeScore is a transparent heuristic, not AI-generated or a calibrated SLA. Review AI interpretations against evidence.
