# RabbitMQ Outage

From the repository root:

```powershell
./chaos-scripts/kill-rabbitmq.ps1
```

The default outage is 60 seconds. The shared runner captures healthy baseline
pages and queue counts, kills only RabbitMQ, and restores it after the duration
limit, a two-module failure threshold, or the manual STOP switch. The persistent
RabbitMQ directory is retained. Recovery requires healthy pages **and** a passing
`rabbitmq-diagnostics check_running`, followed by a second queue snapshot.

A verified ten-second test (`20261010T095002977Z`) found all three read pages
available throughout the outage. RabbitMQ recovery took 14.68 seconds after the
start command. Three durable queues existed before and after: Notifications,
WorkshopManagement, and Invoicing. Their aggregate ready-message count was zero
in both snapshots. The detector found no anomalous page samples.

This does not establish message loss or successful event delivery: an empty
queue can mean no messages were published, messages were consumed, or messages
were lost. To measure delivery behavior, track unique test-event IDs from
publication through each relevant consumer and compare missing, delayed, and
duplicate events across the outage. Also verify write requests and background
worker recovery separately. Do not label this read-only test as proof of no loss.

See [agent documentation](chaos-agent.md) for orchestration and shared controls.
