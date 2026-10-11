# Chaos Agent Findings

Run: 20261010T221900101Z. Mode: Rule-based; no AI used. Execute: True.

Error:

## workshop-delay-high

Recovered: True. Recovery: 0.27 s. Anomalies: 4. Rollback: Maximum fault duration reached.

Evidence run: 20261010T221909587Z. AI status: Not configured.
Read-probe heuristic score: 80.8/100. Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.

Measured anomalies only. No AI findings were generated.

Read probes do not prove write correctness or message durability. ProbeScore is a transparent heuristic, not AI-generated or a calibrated SLA. Review AI interpretations against evidence.
