# Provider failure handling

Reviewed against main `c6af2578521fd590ef0bdff5fa29b5b41d99de4f` on
11 October 2026. The earlier PR #5 is already merged. This follow-up changes only
the provider clients, a small configuration guard, isolated mocked tests and this
document. No PowerShell, watchdog, runner, router, endpoint or integration branch
is changed. Open PR #8 touches the router, configuration, endpoints, AI_SETUP and
shared status documents; those files are deliberately excluded from this work.

## Modes and configuration

| Mode | Completion behavior |
| --- | --- |
| Ollama | Local completion only; no Groq request |
| Groq | Groq only; a failure never silently selects Ollama |
| Auto | Configured Groq first, then Ollama if Groq cannot produce parseable output; deterministic-only if neither works |

The operator's selected mode stays authoritative. This PR does not change defaults
or force Groq mode. Current main defaults: Groq model `openai/gpt-oss-20b`, 60s
completion timeout; Ollama model `qwen3.5:4b`, 240s completion timeout, local base URL
`http://localhost:11434`. Ollama model listing has a separate five-second timeout.
These are source configuration observations, not verified live-provider contracts.

Groq reads `GROQ_API_KEY` from the process environment at call time. Optional
overrides are `GROQ_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`; timeout and Groq
endpoint settings are under `Ai` configuration. Keep keys in private environment
configuration, never source, fixtures or captured output. No CI key is required.
The clients never install or download models.

Both clients reject non-absolute/non-HTTP(S) endpoints, embedded URL credentials,
empty model names and invalid timer intervals before sending HTTP. Timeouts must
be positive and fit CancellationTokenSource's supported timer range. Groq also
rejects whitespace/control characters in its configured key. Diagnostics identify
the setting to fix without echoing endpoints or keys. Invalid local configuration
is a provider failure, so Auto can still use the other configured provider.

## Failure behavior and fixes

- Main already handles refused connections, HTTP failures, malformed envelopes,
  empty content and provider body-read deadlines. Those implementations are reused.
  There are no retries added here. Auto attempts each eligible provider once.
- Caller cancellation propagates and does not trigger fallback. This follow-up
  checks cancellation before missing-key/configuration/model-status work so a
  pre-cancelled call is not misreported as provider unavailability.
- Provider deadline expiry returns a failure. Only Auto may continue to its next
  provider. Request headers and body reading remain under the same completion
  deadline; local model listing is separately bounded.
- Groq 401/403 identifies key/access rejection, 429 identifies quota/rate limit,
  and other HTTP failures retain status. Structured `error.message` remains useful
  for model/configuration diagnostics. The configured key and Bearer/Basic header
  values are redacted **before** the existing 200-character truncation. Control
  characters are normalized. Raw error bodies and transport exception messages
  are not returned. Ollama unreachable status no longer echoes a configured URL.
- Parse success is not safety approval. An incomplete or unsupported recommendation
  is rejected by RecommendationValidator, without using fallback to obscure the
  rejection. The independent run endpoint still requires approval, allowlisted
  targets, duration bounds, preflight, STOP and concurrency checks. Scores and
  recorded recovery decisions remain deterministic.

Evidence for the changes: main's DescribeUpstreamError returned arbitrary
`error.message` text without key redaction; Uri/request/header construction and
CancelAfter could throw for invalid configuration before the existing network
catch blocks; missing-key and invalid-configuration early returns could beat
caller cancellation. The new tests reproduce these cases using synthetic inputs.

## Automated verification

```powershell
dotnet build dashboard/Dashboard.csproj
dotnet test dashboard.Tests --filter 'FullyQualifiedName~ProviderFailureFollowupTests|FullyQualifiedName~UpstreamErrorMessageTests|FullyQualifiedName~ProviderResponseSafetyTests|FullyQualifiedName~ProviderModeTests'
dotnet test dashboard.Tests
git diff --check
```

All provider checks are **unit/mocked**, with HTTP handlers terminating requests
in-process. New tests call the router directly, never host an execution endpoint
or invoke Docker. Existing endpoint tests substitute a fake experiment runner.
Synthetic credentials are restored after tests and never work against a provider.

Final verification: build passed with zero warnings/errors; 51 targeted tests
passed in 47s; all 155 dashboard tests passed in 1m24s, zero failures/skips.
There are 18 new unit/mocked cases. The initial targeted and full runs each failed
one existing aggregate-message length test (50/51 and 154/155 passed). Shortening
the new Ollama diagnostic fixed the regression without changing the test bound.

Coverage includes successful providers/mode isolation (existing tests), Auto HTTP
failure/configuration fallback, both providers unreachable, malformed envelopes,
incomplete/unsafe recommendation rejection, timeout, caller cancellation without
fallback, missing key/model and secret redaction. No stub result is live verification.

## Optional manual live check, not run by CI

Start the existing C# dashboard with privately configured environment settings.
Check `/api/ai/status`; Groq availability there means key presence, not validated
credentials, model access or quota. Select Groq, Ollama or Auto explicitly through
the dashboard. With consent to send the extracted experiment evidence to the
selected provider, request one recommendation. Record only the provider attribution,
success/failure, sanitized status and whether server validation allowed the proposal.
Do not approve or run an experiment. Do not capture keys, headers or raw upstream
messages. Stop the dashboard after the manual check if it was started for this test.

No live Groq or Ollama call was performed for this contribution. Existing historical
Ollama verification does not prove the current environment; Groq remains unverified
live in the repository handover. `docs/GROK_SETUP.md` is absent on this main; use
`AI_SETUP.md` with this provider-specific follow-up.

## Remaining limitations

Full JSON Schema/semantic evidence validation of explanation records is not present:
deserialization can accept missing analysis fields and does not prove prose claims.
Addressing that needs coordinated router/endpoint edits, which overlap PR #8 and
are excluded here. No validator was weakened or new execution authority granted.

Redaction covers the configured key and recognizable authorization values, not
arbitrary secrets encoded or transformed by an upstream server. Structured error
messages remain untrusted diagnostics and are never execution instructions.
Live model support, quota, DNS/TLS/proxy behavior and sustained load are unverified.
The RabbitMQ committed-row/missing-event defect is unchanged and unresolved.
