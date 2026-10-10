# Combined scripts and dashboard contribution

Created on 11 October 2026 from remote main
`0e9b6147e5e1f01c9fd67e672325568311252904`.

The existing C# dashboard and Customer/Vehicle pause scripts now live in one
checkout. Source commits were `75ef90dae6331cac1f2ac9b05f934788fa23d8f3`
(pause scripts, PR #3) and `44535dcf4db1b3c91892462adba9687aa0a0e5fd`
(local dashboard improvements). Both were cherry-picked onto
`feat/combined-scripts-dashboard`; original branches and working files were preserved.
Only the three shared status/progress documents conflicted; both histories were
retained. Earlier entries in those documents describe their own historical branches.

## Integrated behavior

- Both wrapper scripts, shared detached watchdog, fake-Docker tests and scorer
  target mappings are present. CLI defaults remain read-only previews.
- Dashboard prepared cards detect the scripts in the same checkout, show their
  fixed targets/bounds and explain the remaining recovery-verification gate.
- Hyphenated pause report IDs load through the existing report endpoint without
  allowing path traversal. Failed recovery remains false and its error remains
  available to the dashboard; an added unit/mocked regression verifies this path.
- Dashboard controls retain parameter edits, validate bounds, repeat preflight
  before approved actions and block actions on disconnection, STOP or active run.
- Existing C# execution interface is retained. No second dashboard or Python/Node
  agent framework is imported. Node is used only for frontend regression tests.
- The local dashboard's Groq-only default is preserved. Ollama can be explicitly
  enabled through configuration; no provider is called merely by integration.

## Safety and limitations

Pause experiments remain **prepared, not executable through the dashboard**.
`PreparedExperiments` is display metadata, not an execution catalog. This integration
does not replace disposable live pause/unpause, STOP, cleanup-error and hard-parent-
termination proof. The automated script tests use fake Docker and fake HTTP.
Do not mistake their success for real-container rollback verification.

The earlier recovery audit demonstrated parent-owned Start-Job failures in the
existing crash experiments. Those experiments were not modified here. Follow PR #7
before crash demonstrations. RabbitMQ customer committed-row/missing-event divergence
remains unresolved; no outbox or data-semantics change is included.

The original ignored `.env`, STOP and local `.gitignore` edits were not copied or
committed. The launcher can privately load a key only from an existing ignored
`agentic-chaos/.env` in the checkout where it runs. That file does not exist in this
new checkout; use a privately configured environment if needed. No key was requested,
printed or committed. This contribution does not include the separate provider-client
hardening PR #5 or import alternative architectures from PR #2.

## Reproduce

From this combined checkout, using .NET 10, PowerShell 7, Python and Node:

```powershell
dotnet test dashboard.Tests --logger 'console;verbosity=minimal'
$env:CHAOS_TEST_PWSH = (Get-Command pwsh).Source
python chaos-scripts/tests/test_pause_experiments.py
node dashboard.Tests/frontend-tests.cjs
./dashboard/start-local.ps1
```

Starting the dashboard neither requests an AI recommendation nor injects a fault.
Containers created from another checkout are deliberately refused by the scripts'
ownership guards. Do not change those labels or point this checkout at the existing
stack to bypass the guard. No real Pitstop fault is needed to review this integration.

## Verification

- Unit/mocked: 135 .NET tests passed, zero failed/skipped, duration 2m32s.
  Hosting uses a fake experiment runner and stub provider transports.
- Unit/mocked: 12 pause-script tests passed in 186.884s using fake Docker and HTTP,
  including parent death, STOP, thresholds, ownership and scoring.
- Unit/mocked frontend: 36 regression checks passed; all three scripts parsed.
- Static: launcher PowerShell parsing and Git whitespace checks passed.
- Live-system read-only: temporary dashboard on port 5282 returned HTTP 200;
  `/api/state` detected both actual pause scripts, reported each non-executable,
  and honored this checkout's temporary STOP gate. The server was stopped and
  only that temporary gate was removed afterward.
- The original STOP SHA256 remained
  `2E133B02D091FD46C34B0B29E93821A381952EC162ABC2089A31483207861996`.

No disposable-container or live fault test was run for pause experiments. No live
AI request, business write, database change, or browser visual inspection was made.
The first temporary dashboard smoke launch failed because Windows split an assembly
path containing spaces; the repeat used a relative assembly path.

Base/head hashes, smoke-test result and exact changed files are included in the
integration PR. The original script PR #3 stays open and untouched; this combined
PR includes its changes, so review them as overlapping contributions rather than
merging both independently without checking the resulting diff.
