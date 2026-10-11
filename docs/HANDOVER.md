# START HERE

> **Current state lives in `docs/AI_WORK_CHECKPOINT.md`, and the
> requirement-by-requirement evidence in `docs/REQUIREMENTS_EVIDENCE.md`.**
> If anything below disagrees with those two or with `git log`, trust them.

Recovery document for whichever coding agent picks this up next. Everything
below was verified by running it.

**Last updated: 2026-10-11, commit `6b8ead1`.**

## State in one paragraph

Five executable experiments (`kill-service`, `kill-rabbitmq`, `network-delay`,
`packet-loss`, `kill-database`), 193 tests and 56 recovery-contract assertions
passing, 29 recorded runs, a resilience console with nine milestone areas and a
baseline/impact/recovery chart drawn from real samples, and all five submission
deliverables written. **Ollama is verified end to end through the real
dashboard workflow** (HTTP 200, `provider: ollama`, `allowed: true`).
**Groq is UNVERIFIED end to end** - see the checkpoint for the single command
that would settle it. No video has been recorded.

## Where things are

| | |
| --- | --- |
| Repository | `C:\Users\Saurabh\pitstop` |
| Remote | https://github.com/saurabhshreni-cmyk/bosch-chaos-hackathon |
| Branch | `main`, synchronised with `origin/main` |
| Latest commit | `git log --oneline -1` — most recent work is the publish-integrity finding |
| Working tree | Clean apart from gitignored `chaos-scripts/results/` and build output |
| Checkpoint tags | `baseline-phase0` (verified baseline, `a6bc383`) and `pre-groq-migration` |
| Branch fork | **Decided:** adapt techniques from PR #2, do not merge it. Their branches are untouched. A new one, `Jigisha-Pradhan-patch-1`, has appeared and is also untouched. |
| Platform work | Phases 0-5 complete; Phase 6 partly done (137 tests). Watchdog defects fixed and verified. |
| PR #1 | **Merged** as `12a5245`. No open PRs. |
| `feature/kill-rabbitmq` | **Deleted** — its one unique behaviour was ported first (`d4685e5`) |
| `task2-kill-service` | PR #1's merged branch, still present. Safe to delete; nobody asked. |

An untracked nested clone sits at `pitstop/`. Scratch duplicate, gitignored,
nothing depends on it. Leave it.

## Start everything

Stack (13 containers): `docker compose -f src/docker-compose.yml ps`

`network-delay` needs its sidecar image, built once:

```powershell
docker build -t pitstop-netem:1.0 chaos-scripts/netem-image
```

If an experiment ever leaves traffic shaping behind, this clears it:

```powershell
docker compose -f src/docker-compose.yml restart workshopmanagementapi
```

Cold start, from `src/`, base images first and in order:

```bash
docker build -t pitstop-dotnet-sdk-base:1.0 . -f dotnet-sdk-base-dockerfile
docker build -t pitstop-dotnet-runtime-base:1.0 . -f dotnet-runtime-base-dockerfile
docker build -t pitstop-dotnet-aspnet-base:1.0 . -f dotnet-aspnet-base-dockerfile
docker compose up -d --build
```

Dashboard. The AI layer works out of the box via local Ollama; set
`GROQ_API_KEY` for the faster cloud path. See `docs/AI_SETUP.md`:

```powershell
dotnet run --project dashboard/Dashboard.csproj --urls http://localhost:5280
```

Tests:

```powershell
dotnet test dashboard.Tests
```

**Dashboard: http://localhost:5280** · Site 7005 · RabbitMQ 15672 · MailDev 4000 · Seq 5341.

`docker compose down` to stop. **Never `-v`** — it deletes `sqlserverdata` and
every database in it.

## Run things from the command line

```powershell
./chaos-scripts/map-dependencies.ps1                          # map; read-only
./chaos-scripts/kill-service.ps1 -DurationSeconds 30          # Workshop crash
./chaos-scripts/kill-rabbitmq.ps1                             # dry run, changes nothing
./chaos-scripts/kill-rabbitmq.ps1 -DowntimeSeconds 25 -Execute
./chaos-scripts/network-delay.ps1 -DurationSeconds 20 -DelayMilliseconds 400
./chaos-scripts/analyze.ps1                                   # agent; read-only, no network
./chaos-scripts/test-publish-integrity.ps1 -Writes 20         # regression test
```

Kill switch, from a second terminal at the repo root (or the dashboard button):

```powershell
New-Item chaos-scripts/STOP -ItemType File -Force
```

Delete it before the next run or every experiment refuses to start.

## The integrity finding — fixed, with one part still open

Full write-up in `docs/publish-integrity.md`.

**What was wrong.** On a *healthy* system, 30% of customer registrations
returned 500 with the row committed and no event published. Cause: the
publisher was registered `AddTransient` (new publisher and connection per
request) and `Connect()` was accidentally `async void`, so every request raced
a half-built connection and often threw `NullReferenceException` — after
`SaveChangesAsync` had committed.

**Why it was hard to fix.** `src/Infrastructure.Messaging/` was consumed as a
published NuGet package, so editing it changed nothing at runtime. Verified by
rebuilding and force-recreating the containers and seeing the same exception.

**Fixed (option A).** All nine services now reference the library by project,
the Dockerfiles build from the `src/` context, and the compose build stanzas
were widened. Measured with `test-publish-integrity.ps1`:

| | Before | After |
| --- | --- | --- |
| Divergent writes | 6 of 20 (30%) | **0 of 30 (0%)** |
| Exit code | 1 FAIL | **0 PASS** |

**Still open: durability (option C).** A genuine broker outage still diverges —
`kill-rabbitmq.ps1` after the fix still reports `DivergenceDetected`, because
the write commits before the publish is attempted. That needs a transactional
outbox and is the largest remaining piece of work.

## Verified by running it

**Day 1, reproduced from `main` after the merge**
- 13 containers up; the health-checked ones healthy.
- Compose valid, single top-level `volumes:` key.
- Map: 13 nodes, 40 edges.
- `kill-service`: max-duration, **threshold** and manual kill switch rollbacks.
- Remote-endpoint guard refused to run with `DOCKER_HOST` set to a working endpoint.
- `kill-rabbitmq`: dry run, baseline abort, max-duration, manual kill switch; recovery 19.28s.

**Dashboard, end to end through the UI**
- Approved and injected `kill-service`; watched Workshop time out at ~6s while
  Customer and Vehicle held ~15ms; saw the container pass through `starting`;
  confirmed recovery; run landed in history; assessment refreshed itself.
- Kill switch from the dashboard aborted a 55s run at 21.3s, recovered, audited.
- Rejected: missing approval, non-allowlisted experiment, out-of-bounds duration,
  path traversal on `/api/runs`, and starting while STOP is present.

**Integrity**
- 6 of 20 writes divergent on a healthy system; `CustomerId` is the primary key,
  so a same-id retry 500s and a new-id retry duplicates the person.

## Not done

- **Groq end to end.** Its provider path returns 200 and its schema is
  strict-compliant (checked offline), but no dashboard recommendation has
  reported `provider: groq`. The last 400 came from a stale running build that
  predated the `max_completion_tokens` fix. Ollama **is** verified end to end.
- **Durable publishing (transactional outbox).** The spurious 30% is fixed; a
  real broker outage still loses the event. This is the one open High finding.
- **A hung process has never been injected.** `pause-customer-api` and
  `pause-vehicle-api` stay `PREPARED - NOT REGISTERED - NOT EXECUTABLE`: a
  paused container stays paused and no unpause watchdog exists. The run
  endpoint refuses them by name, verified.
- **Threshold rollback untested in `kill-rabbitmq.ps1`** - pages stay healthy
  during a broker outage so nothing trips it. Verified in `kill-service.ps1`.
- The broker experiment infers non-delivery from the broker being down rather
  than inspecting consumer state.
- No load generator, so every measurement is from a near-idle system and is a
  floor rather than a production figure.
- The dashboard polls every 2–2.5s rather than streaming. Live, but not push.
- **No demo video recorded.** The script is `docs/DEMO_SCRIPT.md`.

## Highest-priority next action

Start the dashboard from current `main` **in a window that has
`GROQ_API_KEY` set in that same window**, and request one recommendation. A key
set elsewhere is not inherited by the dashboard's process. If the provider badge
reads `groq`, Groq is verified; if it 400s, capture the `failed_generation`
tail the current build surfaces. Either way Ollama answers, so nothing is
blocked on it.

After that, the transactional outbox (option C in `docs/publish-integrity.md`),
which is the one part of the integrity problem still open.

## Safety rules

- Experiments target **only** containers in this Compose project. Both scripts
  enforce a local Windows named-pipe context and refuse a remote `DOCKER_HOST`.
  Tested.
- The dashboard cannot run an arbitrary command: fixed allowlist, integer
  parameters with bounds, explicit approval flag, no overlapping runs.
- The kill switch is a file the scripts poll for. **Keep every model off the
  rollback path, and off every number in the report.**
- `src/*/appsettings.Production.json` carries the upstream sample's hardcoded SQL
  and RabbitMQ passwords. Sandbox-only, inherited from EdwinVW/pitstop. Do not
  imitate and never put a real secret there.

## Open pull requests

#4, #5, #6 and #7 are merged. **#8 and #3 have named defects and must not be
merged as-is** - see `docs/PR_REVIEW_LOG.md`. #8 would silently send an
Ollama-only operator's requests to Groq. Teammate branches are untouched.

