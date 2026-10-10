# Workshop Network Delay

Download the helper once, then run from the repository root:

```powershell
docker pull nicolaka/netshoot:v0.13
./chaos-scripts/network-delay.ps1
```

The script adds 500 ms of egress delay to Workshop API's `eth0` using Linux
`tc netem`. A temporary helper shares only that container's network namespace
and uses NET_ADMIN. It does not change the host network or require tools inside
the application image. The runner refuses an existing non-default root queue
and owns handle `28:`. The watchdog and cleanup remove this rule automatically.

Normal duration is 30 seconds. Customer or Vehicle failure/excessive latency,
the STOP switch, or the time limit restores the network early. Requests to SQL
Server and RabbitMQ also traverse this interface, so UI latency can increase
by much more than 500 ms. Existing loaded pages need refreshing to show impact.

In the verified controller run `20261010T094655220Z`, Workshop requests took
approximately 4.55 and 3.84 seconds, with two other probes timing out at the
five-second limit. Customer and Vehicle remained healthy. After removing the
rule, Workshop returned in approximately 26.5 ms and the full recovery round
took 0.06 seconds. Four anomalous samples were detected.

The script does not simulate packet loss or a full network partition. If a host
or PowerShell crash prevents cleanup, restart Workshop API to recreate its
network namespace, then verify the rule is gone before another experiment.
See [agent documentation](chaos-agent.md) for details and limitations.
