# Three-agent integration contract

Implementation starts from PFIA commit `c16a830` on `feat/three-agent-platform`.
Remote main was refreshed to `d6a3eb5` and merged into this feature branch as
`259b6965`; main itself was not modified. PFIA PR #10 remains an unmerged prerequisite.
Its existing files therefore also appear in a main-targeted PR until that prerequisite merges.
The existing analysis agent, discovery, scoring and Groq validation remain authoritative.

The new workflow consumes recorded recommendations. It persists immutable proposals,
expiring approvals, execution leases and recovery events in separate SQLite tables.
History retention must never delete an active rollback lease. A separate worker owns
execution; HTTP requests never wait for an experiment or inject a fault themselves.

Execution is disabled by default. Only explicitly configured Compose projects named
`pfia-disposable-*`, with disposable container labels and validated Compose ownership,
may execute. The current Pitstop `src` project is forbidden. Operator authentication,
project-owned internal networks without foreign peers and loopback-only published ports,
target allowlists, bounded durations, functional baseline probes and an independent
Docker watchdog are mandatory. Recommendations and AI text are never approval.

Initial executable adapter: stop one or several previously running, approved containers
and start the same immutable container IDs during rollback. RabbitMQ availability can
use that adapter. Database, network, CPU and memory faults remain unsupported until
their additional isolation/tooling and rollback requirements have been demonstrated.
No existing PowerShell experiment or recovery file will be changed.
Current main includes packet-loss and database scripts; they are deliberately not
wrapped here because their isolated ownership, data and rollback contracts still need
verification through this authenticated workflow.

The watchdog is a separate Docker container using a fixed script, an existing local
Docker CLI image and the Docker socket. It starts original containers on deadline or
abort even if all Python processes disappear. The socket grants substantial authority;
this is restricted to a disposable local Docker environment, never production.

Self-healing uses deterministic recovery playbooks. Groq may explain compact evidence
but cannot select unrestricted actions, issue shell commands or change safety decisions.
Application verification and stability evidence are separate from infrastructure state.
Missing dependency/functionality evidence means inconclusive recovery, never success.

Tests use mocked infrastructure only. No live fault injection is authorized by this
implementation request. Independent process-death rollback and actual fault adapters
must be verified in a separately approved disposable environment before claiming live
recovery reliability. The RabbitMQ/customer committed-row/event-publication defect
remains unresolved; restarting RabbitMQ cannot repair it.
