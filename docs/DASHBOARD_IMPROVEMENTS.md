# Resilience dashboard integration

Updated 2026-10-11 on feat/dashboard-integration, based on main 0e9b614.
The current console remains the C# dashboard on port 5280.

## Changes

- Prepared Customer and Vehicle API pause cards show fixed targets, duration
  limits, recovery behavior, local script availability and pending live validation.
  They have no execution controls and remain outside ExperimentCatalog.
- Running containers, measured module health, activity, history and STOP have
  summary cards. Section navigation, responsive tables, keyboard access and
  measured-health graph colors remain in place.
- Polling preserves edited duration and network-delay values. Both parameters
  require whole numbers inside catalog bounds before preflight.
- Disconnected, STOP and active-run states disable manual and AI approval.
  Rejected recommendations cannot run. AI approvals repeat preflight and show
  the catalog latency in the card and confirmation.
- Groq-only installations expose only the Groq mode and never call Ollama.
  Provider, discovery, evidence and error text are escaped before HTML rendering.
- Report lookups support timestamp IDs with the new pause-script suffix while
  rejecting path separators and traversal.
- The current injected runner from main remains the only execution path.
  Tests replace it and use individual runtime directories for STOP, audit,
  provider settings and reports.
- Character encoding in visible UI text is repaired and asset versions refreshed.

## Verification

134 .NET tests passed with no failures or skips.
36 frontend regression checks passed through the Node VM DOM adapter.
HTML IDs and script asset references passed structural checks.
The launcher's PowerShell syntax and Git whitespace checks passed.
The real STOP checksum stayed unchanged during the final isolated test runs.

Localhost ports 5280, 8000 and 8501 remain stopped. No live fault or
application-specific Groq request was performed. Visual browser inspection and
a real launcher invocation were not performed in this update.

## Start when ready

From the repository root:

    ./dashboard/start-local.ps1

The launcher selects installed or workspace-local .NET, adds local PowerShell
and Docker tools to PATH, and uses an existing GROQ_API_KEY. If the process has
no key, it can load GROQ_API_KEY from the ignored agentic-chaos/.env.
It reports only whether a key is configured and never prints its value.
Starting the console does not request a recommendation or inject a fault.

To run the frontend checks with Node installed:

    node dashboard.Tests/frontend-tests.cjs

PR #3 contains the prepared pause scripts. Their live cleanup proof remains a
separate step before enabling them in the dashboard execution catalog.
