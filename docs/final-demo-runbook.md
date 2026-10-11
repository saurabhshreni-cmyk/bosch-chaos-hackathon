# Final Demo Runbook

Use this order for the instructor demo. Keep the demo focused on the required
Day-2 story: AI planning, three controlled failures, measurements, recovery,
ranked findings, and the five deliverables.

## 1. Start The Application

From the repository root:

```powershell
cd src
docker compose up -d --build
docker compose ps -a
cd ..
```

Wait until SQL Server, RabbitMQ, WebApp, Customer API, Vehicle API, and Workshop
API are running. Open:

- Pitstop app: http://localhost:7005
- Customer: http://localhost:7005/CustomerManagement
- Vehicle: http://localhost:7005/VehicleManagement
- Workshop: http://localhost:7005/WorkshopManagement

## 2. Clear Demo Data

Run this only when you want a clean garage before the live walkthrough:

```powershell
docker cp src\scripts\ClearDatabases.sql sqlserver:/tmp/ClearDatabases.sql
docker exec sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "8jkGh47hnDw89H@q8LN2" -C -i /tmp/ClearDatabases.sql
```

Optional verification:

```powershell
docker exec sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "8jkGh47hnDw89H@q8LN2" -C -Q "SET NOCOUNT ON; SELECT 'CustomerManagement.Customer' AS TableName, COUNT(*) AS RowsLeft FROM CustomerManagement.dbo.Customer UNION ALL SELECT 'VehicleManagement.Vehicle', COUNT(*) FROM VehicleManagement.dbo.Vehicle UNION ALL SELECT 'WorkshopManagement.MaintenanceJob', COUNT(*) FROM WorkshopManagement.dbo.MaintenanceJob;"
```

## 3. Start Local AI And Dashboard

In one terminal:

```powershell
ollama serve
```

If the model is missing:

```powershell
.\agent\setup-ai.ps1
```

In another terminal:

```powershell
cd dashboard
npm install
npm start
```

Open the printed dashboard URL, normally http://127.0.0.1:7010.
By default the dashboard starts with a clean session list and does not show
retained historical evidence. If you need to present the packaged retained run
instead, start it like this:

```powershell
$env:DASHBOARD_SHOW_RETAINED = '1'
npm start
```

## 4. Show The Required Evidence

1. Open Pitstop and show the three module pages are healthy.
2. Open the dashboard Overview.
3. If presenting retained evidence, select the completed AI run from
   `submission/manifest.json`: `20261010T215606032Z`.
4. Show the agent lifecycle and worker statuses.
5. Show the latency chart and three experiment results:
   - Workshop crash
   - Database crash / SQL dependency outage
   - Workshop network delay
   For a live rerun, keep RabbitMQ crash unchecked. The required three
   scenarios are covered by the checked defaults above, and broker-write
   durability needs a separate tracked write test.
6. Open Dependencies and explain the mapped services, SQL, RabbitMQ, and WebApp.
7. Open Evidence & findings and show:
   - baseline evidence
   - measured anomalies
   - ranked AI findings
   - recommended fixes
8. Open `submission/architecture.pdf` and confirm it is one page.
9. Play `submission/demo.webm`; it is under three minutes.
10. Open `submission/findings.md` and `submission/team-form.json`.

## 5. What To Say Carefully

- The failures are controlled local sandbox experiments, not production tests.
- The AI ranks allowed experiments and selects explanations from bounded
  evidence; findings are hypotheses that need human review.
- The resilience score is a transparent read-probe heuristic, not an SLA.
- Full disk and overloaded database are documented as future/proposed scenarios,
  not implemented live injectors.

## 6. Before Submission

Regenerate the final artifacts after all last-minute edits:

```powershell
cd dashboard
node package-submission.mjs 20261010T215606032Z 20261010T222301763Z 20261010T172435409Z
cd ..
```

Create a fresh zip after the artifacts regenerate:

```powershell
Compress-Archive -Force -Path README.md,submission\demo.webm,submission\demo.vtt,submission\architecture.pdf,submission\findings.md,submission\team-form.json,submission\manifest.json,submission\verification.json,docs\final-demo-runbook.md -DestinationPath submission\team28-submission.zip
```

Then submit these five items through the official portal:

- repository link and README
- `submission/demo.webm`
- `submission/architecture.pdf`
- `submission/findings.md`
- `submission/team-form.json`
