# Day 1 Evidence

Verified locally on October 10, 2026. This is a measured-results summary, not
an AI-generated findings report.

## Steady Baseline

[Saved baseline](evidence/day1/baseline.json) contains a three-minute run with
86 sequential read samples per module and zero failures. Recorded p95 latency:

| Module | Samples | Failures | p95 latency |
| --- | --- | --- | --- |
| Customer | 86 | 0 | 96.10 ms |
| Vehicle | 86 | 0 | 77.66 ms |
| Workshop | 86 | 0 | 73.09 ms |

## Sequential Controller Run

Session `20261010T094541654Z` completed in explicit rule-based mode (no AI).

| Experiment | Evidence run | Observed impact | Recovery after restore command |
| --- | --- | --- | --- |
| Workshop crash | 20261010T094549311Z | Workshop timeouts/offline fallback; Customer and Vehicle stayed available | 1.24 s |
| Database crash | 20261010T094623698Z | Customer and Vehicle timeouts triggered two-module rollback | 15.43 s |
| Network delay | 20261010T094655220Z | Workshop slowdowns/timeouts; Customer and Vehicle stayed available | 0.06 s |

RabbitMQ was tested separately: see [broker results](kill-rabbitmq.md). Manual
STOP and threshold rollback were tested in the original Workshop runs; see
[Workshop evidence](kill-service.md).

Selected JSON/CSV artifacts are saved in [the evidence folder](evidence/day1/).
Other generated runs remain local and ignored by Git. These results cover page reads; the full garage write
workflow, event delivery, and background processing need separate evidence.
