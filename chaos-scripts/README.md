# Chaos scripts

These scripts use the current main-branch PowerShell conventions: fixed targets,
bounded faults, baseline/fault/recovery probes, STOP, and CSV/JSON evidence.
The Customer and Vehicle pause experiments reuse ChaosSafety.psm1 and the same
experiment.lock as kill-service, kill-rabbitmq, and network-delay.

## New experiments

| Script | Fixed target | Fault | Default / maximum |
| --- | --- | --- | --- |
| pause-customer-api.ps1 | customermanagementapi | Freeze container processes | 15 / 60 seconds |
| pause-vehicle-api.ps1 | vehiclemanagementapi | Freeze container processes | 15 / 60 seconds |

Pause simulates an API that remains running but stops responding. It tests
timeouts and isolation without killing or restarting the process. It does not
exercise the write path or prove data integrity.

Run from the repository root using PowerShell 7 on Windows with Docker Desktop:

~~~powershell
# Read-only previews. These work with STOP engaged.
./chaos-scripts/pause-customer-api.ps1
./chaos-scripts/pause-vehicle-api.ps1

# Deliberate fault injection in the disposable local sandbox only.
# Requires STOP to be absent and all module pages healthy.
./chaos-scripts/pause-customer-api.ps1 -DurationSeconds 15 -Execute
./chaos-scripts/pause-vehicle-api.ps1 -DurationSeconds 15 -Execute
~~~

The repository's existing STOP file has been preserved. Engaging it during a
run aborts the fault. Neither dry runs nor these instructions clear it.

## Execution and recovery

Only one container from this checkout's src/docker-compose.yml is eligible.
Remote Docker endpoints, endpoint overrides, stopped or already-paused targets,
and containers belonging to another checkout are refused. Calls pin the local
named-pipe endpoint so a context change cannot redirect rollback.

Three module pages on 127.0.0.1:7005 provide the baseline and recovery checks.
An unhealthy baseline prevents injection. An unhealthy or slow non-target page
aborts the fault. Defaults are a 3-second request timeout, three baseline rounds,
a 3000ms latency threshold, and 90 seconds for measured recovery.

A detached PowerShell process owns experiment.lock before injection. It checks
STOP, the duration deadline, and the parent's PID plus creation time. It unpauses
only the verified target and retries if Docker is unavailable. It retains the
lock until recovery is confirmed. A failed rollback never cancels the watchdog.
If a runner dies, the watchdog checks module-page recovery itself.

Each executed attempt writes results/<run-id>/samples.csv and report.json.
The watchdog additionally writes watchdog-report.json or watchdog-errors.log.
An error before a target is resolved may exit before an evidence directory exists.
Dry runs do not create evidence or change container state.
The deterministic scorer recognizes both API targets and excludes their own
fault probes from blast-radius containment; write-path integrity stays unmeasured.

If recovery cannot complete, keep STOP engaged, inspect the evidence and verify
Docker is available. For manual rollback, first check ownership using:

~~~powershell
docker compose -f src/docker-compose.yml ps
docker compose -f src/docker-compose.yml unpause customermanagementapi
# Or, for the Vehicle experiment:
docker compose -f src/docker-compose.yml unpause vehiclemanagementapi
~~~

Do not clear a runtime lock while its watchdog is still recovering a target.

## Tests and registration

~~~powershell
python chaos-scripts/tests/test_pause_experiments.py
~~~

Put pwsh on PATH or set CHAOS_TEST_PWSH to its executable. Tests use temporary
checkouts, fake Docker, fake HTTP and synthetic reports. No application container
is paused. They check dry runs, baseline/STOP refusal, ownership, local endpoint
restrictions, locking, normal/error rollback, threshold abort, hard parent death,
and deterministic target scoring.

These scripts are prepared for CLI use and intentionally remain outside
ExperimentCatalog. Register them only after live cleanup has been verified in
the disposable sandbox, including STOP, errors and orchestrator termination,
as required by the main-branch experiment registration convention.
