# Discovered Pitstop service inventory

Generated from this checkout by `python -m tools.export_inventory`. Configuration evidence only; not a live-state or recovery claim.

| Service | Framework / role | Compose ports | Replicas | Limits | Restart | Health route |
| --- | --- | --- | ---: | --- | --- | --- |
| rabbitmq | infrastructure image / infrastructure | 15672:15672, 5672:5672 | 1 | not configured | not configured | Compose check |
| sqlserver | infrastructure image / infrastructure | 1434:1433 | 1 | not configured | not configured | Compose check |
| mailserver | infrastructure image / infrastructure | 25:25, 4000:80 | 1 | not configured | not configured | not discovered |
| logserver | infrastructure image / infrastructure | 5341:80 | 1 | not configured | not configured | not discovered |
| vehiclemanagementapi | ASP.NET Core / application | 5000 | 1 | not configured | not configured | /hc |
| customermanagementapi | ASP.NET Core / application | 5100 | 1 | not configured | not configured | /hc |
| workshopmanagementapi | ASP.NET Core / application | 5200 | 1 | not configured | not configured | /hc |
| auditlogservice | .NET worker / application | not published | 1 | not configured | not configured | not discovered |
| invoiceservice | .NET worker / application | not published | 1 | not configured | not configured | not discovered |
| notificationservice | .NET worker / application | not published | 1 | not configured | not configured | not discovered |
| timeservice | .NET worker / application | not published | 1 | not configured | not configured | not discovered |
| workshopmanagementeventhandler | .NET worker / application | not published | 1 | not configured | not configured | not discovered |
| webapp | ASP.NET Core / application | 7005:7005 | 1 | not configured | not configured | /hc |

## rabbitmq

Runtime: rabbitmq. Networks: default.

Dockerfile: image only. Build images: not applicable.

Environment names only: RABBITMQ_CONFIG_FILE.

Detected controls: none established by these checks.

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:

Source locations:

## sqlserver

Runtime: mcr.microsoft.com/mssql/server. Networks: default.

Dockerfile: image only. Build images: not applicable.

Environment names only: ACCEPT_EULA, MSSQL_PID, MSSQL_SA_PASSWORD.

Detected controls: none established by these checks.

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:

Source locations:

## mailserver

Runtime: maildev/maildev. Networks: default.

Dockerfile: image only. Build images: not applicable.

Environment names only: none in Compose/Dockerfile.

Detected controls: none established by these checks.

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:

Source locations:

## logserver

Runtime: datalust/seq. Networks: default.

Dockerfile: image only. Build images: not applicable.

Environment names only: ACCEPT_EULA, SEQ_FIRSTRUN_NOAUTHENTICATION.

Detected controls: none established by these checks.

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:

Source locations:

## vehiclemanagementapi

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/VehicleManagementAPI/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-aspnet-base:1.0.

Environment names only: ASPNETCORE_ENVIRONMENT, ASPNETCORE_URLS.

Detected controls: delayed retry found; inspect bound and duration; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): /api/[controller], {licenseNumber}.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:55`. Startup ordering only; runtime availability is not established by this edge.
- sqlserver (startup, high): `src/docker-compose.yml:55`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/VehicleManagementAPI/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- sqlserver (database, high): `src/VehicleManagementAPI/appsettings.Production.json:9`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/VehicleManagementAPI/appsettings.Production.json:18`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous publishes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/VehicleManagementAPI/Program.cs`
- `src/VehicleManagementAPI/VehicleManagementAPI.csproj`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/VehicleManagementAPI/Dockerfile`

## customermanagementapi

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/CustomerManagementAPI/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-aspnet-base:1.0.

Environment names only: ASPNETCORE_ENVIRONMENT, ASPNETCORE_URLS.

Detected controls: delayed retry found; inspect bound and duration; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): /api/[controller], {customerId}.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:70`. Startup ordering only; runtime availability is not established by this edge.
- sqlserver (startup, high): `src/docker-compose.yml:70`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/CustomerManagementAPI/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- sqlserver (database, high): `src/CustomerManagementAPI/appsettings.Production.json:9`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/CustomerManagementAPI/appsettings.Production.json:18`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous publishes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/CustomerManagementAPI/CustomerManagementAPI.csproj`
- `src/CustomerManagementAPI/Program.cs`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/CustomerManagementAPI/Dockerfile`

## workshopmanagementapi

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/WorkshopManagementAPI/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-aspnet-base:1.0.

Environment names only: ASPNETCORE_ENVIRONMENT, ASPNETCORE_URLS.

Detected controls: delayed retry found; inspect bound and duration; retry found; inspect policy; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): /api/[controller], customers, customers/{customerId}, vehicles, vehicles/{licenseNumber}, {planningDate}, {planningDate}/jobs, {planningDate}/jobs/{jobId}, {planningDate}/jobs/{jobId}/finish.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:85`. Startup ordering only; runtime availability is not established by this edge.
- sqlserver (startup, high): `src/docker-compose.yml:85`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/WorkshopManagementAPI/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- sqlserver (database, high): `src/WorkshopManagementAPI/appsettings.Production.json:9`. Configured runtime dependency; actual failure impact requires verification.
- sqlserver (database, high): `src/WorkshopManagementAPI/appsettings.Production.json:10`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/WorkshopManagementAPI/appsettings.Production.json:19`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous publishes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/WorkshopManagementAPI/Program.cs`
- `src/WorkshopManagementAPI/WorkshopManagementAPI.csproj`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/WorkshopManagementAPI/Dockerfile`

## auditlogservice

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/AuditlogService/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-runtime-base:1.0.

Environment names only: DOTNET_ENVIRONMENT.

Detected controls: delayed retry found; inspect bound and duration; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:100`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/AuditlogService/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/AuditlogService/appsettings.Production.json:23`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous subscribes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/AuditlogService/AuditlogService.csproj`
- `src/AuditlogService/AuditLogWorker.cs`
- `src/AuditlogService/Program.cs`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/AuditlogService/Dockerfile`

## invoiceservice

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/InvoiceService/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-runtime-base:1.0.

Environment names only: DOTNET_ENVIRONMENT.

Detected controls: delayed retry found; inspect bound and duration; retry found; inspect policy; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:112`. Startup ordering only; runtime availability is not established by this edge.
- sqlserver (startup, high): `src/docker-compose.yml:112`. Startup ordering only; runtime availability is not established by this edge.
- mailserver (startup, high): `src/docker-compose.yml:112`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/InvoiceService/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- sqlserver (database, high): `src/InvoiceService/appsettings.Production.json:11`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/InvoiceService/appsettings.Production.json:23`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous subscribes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/InvoiceService/InvoiceService.csproj`
- `src/InvoiceService/InvoiceWorker.cs`
- `src/InvoiceService/Program.cs`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/InvoiceService/Dockerfile`

## notificationservice

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/NotificationService/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-runtime-base:1.0.

Environment names only: DOTNET_ENVIRONMENT.

Detected controls: delayed retry found; inspect bound and duration; retry found; inspect policy; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:128`. Startup ordering only; runtime availability is not established by this edge.
- sqlserver (startup, high): `src/docker-compose.yml:128`. Startup ordering only; runtime availability is not established by this edge.
- mailserver (startup, high): `src/docker-compose.yml:128`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/NotificationService/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- sqlserver (database, high): `src/NotificationService/appsettings.Production.json:11`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/NotificationService/appsettings.Production.json:29`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous subscribes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/NotificationService/NotificationService.csproj`
- `src/NotificationService/NotificationWorker.cs`
- `src/NotificationService/Program.cs`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/NotificationService/Dockerfile`

## timeservice

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/TimeService/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-runtime-base:1.0.

Environment names only: DOTNET_ENVIRONMENT.

Detected controls: delayed retry found; inspect bound and duration; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:144`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/TimeService/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/TimeService/appsettings.Production.json:18`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous publishes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/TimeService/Program.cs`
- `src/TimeService/TimeService.csproj`
- `src/TimeService/TimeWorker.cs`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/TimeService/Dockerfile`

## workshopmanagementeventhandler

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/WorkshopManagementEventHandler/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-runtime-base:1.0.

Environment names only: DOTNET_ENVIRONMENT.

Detected controls: delayed retry found; inspect bound and duration; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:
- rabbitmq (startup, high): `src/docker-compose.yml:156`. Startup ordering only; runtime availability is not established by this edge.
- sqlserver (startup, high): `src/docker-compose.yml:156`. Startup ordering only; runtime availability is not established by this edge.
- rabbitmq (broker, high): `src/WorkshopManagementEventHandler/appsettings.Production.json:3`. Configured runtime dependency; actual failure impact requires verification.
- sqlserver (database, high): `src/WorkshopManagementEventHandler/appsettings.Production.json:16`. Configured runtime dependency; actual failure impact requires verification.
- logserver (logging, high): `src/WorkshopManagementEventHandler/appsettings.Production.json:28`. Configured runtime dependency; actual failure impact requires verification.
- rabbitmq (broker, medium): `chaos-scripts/dependency-overlay.json:1`. Asynchronous subscribes; disconnection may delay processing rather than make all endpoints unavailable.

Source locations:
- `src/WorkshopManagementEventHandler/EventHandlerWorker.cs`
- `src/WorkshopManagementEventHandler/Program.cs`
- `src/WorkshopManagementEventHandler/WorkshopManagementEventHandler.csproj`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/WorkshopManagementEventHandler/Dockerfile`

## webapp

Runtime: .NET net10.0. Networks: default.

Dockerfile: src/WebApp/Dockerfile. Build images: pitstop-dotnet-sdk-base:1.0, pitstop-dotnet-aspnet-base:1.0.

Environment names only: ASPNETCORE_ENVIRONMENT, ASPNETCORE_URLS, NODE_VERSION, PNPM_VERSION.

Detected controls: delayed retry found; inspect bound and duration; retry found; inspect policy; using/disposal syntax found (not proof of complete cleanup).

Route attributes (may require controller-prefix composition): none discovered.

Configured dependencies:
- customermanagementapi (startup, high): `src/docker-compose.yml:170`. Startup ordering only; runtime availability is not established by this edge.
- vehiclemanagementapi (startup, high): `src/docker-compose.yml:170`. Startup ordering only; runtime availability is not established by this edge.
- workshopmanagementapi (startup, high): `src/docker-compose.yml:170`. Startup ordering only; runtime availability is not established by this edge.
- logserver (logging, high): `src/WebApp/appsettings.Production.json:9`. Configured runtime dependency; actual failure impact requires verification.
- customermanagementapi (http, high): `src/WebApp/appsettings.Production.json:17`. Configured runtime dependency; actual failure impact requires verification.
- vehiclemanagementapi (http, high): `src/WebApp/appsettings.Production.json:18`. Configured runtime dependency; actual failure impact requires verification.
- workshopmanagementapi (http, high): `src/WebApp/appsettings.Production.json:19`. Configured runtime dependency; actual failure impact requires verification.

Source locations:
- `src/WebApp/Program.cs`
- `src/WebApp/WebApp.csproj`
- `src/Infrastructure.Messaging/Infrastructure.Messaging.csproj`
- `src/WebApp/Dockerfile`
