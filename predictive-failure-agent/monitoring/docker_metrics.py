"""Only list/inspect/stats are used. No exec, lifecycle or Docker write API."""
import time
from agent.schemas import Metric


def parse_stats(name, container_id, attrs, stats):
    current = stats.get("cpu_stats", {})
    previous = stats.get("precpu_stats", {})
    cpu_delta = current.get("cpu_usage", {}).get("total_usage", 0) - previous.get("cpu_usage", {}).get("total_usage", 0)
    system_delta = current.get("system_cpu_usage", 0) - previous.get("system_cpu_usage", 0)
    cpus = current.get("online_cpus") or len(current.get("cpu_usage", {}).get("percpu_usage", [])) or 1
    cpu = max(0, cpu_delta / system_delta * cpus * 100) if previous.get("system_cpu_usage") and system_delta > 0 and cpu_delta >= 0 else None
    memory = stats.get("memory_stats", {})
    cache = memory.get("stats", {}).get("inactive_file", memory.get("stats", {}).get("total_inactive_file", 0))
    networks = stats.get("networks", {})
    state = attrs.get("State", {})
    limit = attrs.get("HostConfig", {}).get("Memory", 0)
    return Metric(component=name, container_id=container_id, timestamp=time.time(), state=state.get("Status", "unknown"), health=state.get("Health", {}).get("Status", "not configured"), cpu_percent=cpu, memory_bytes=max(0, memory.get("usage", 0) - cache), configured_memory_limit=limit or None, stats_memory_limit=memory.get("limit"), restart_count=attrs.get("RestartCount", 0), network_rx_bytes=sum(n.get("rx_bytes", 0) for n in networks.values()), network_tx_bytes=sum(n.get("tx_bytes", 0) for n in networks.values()))


def collect(allowed_services, project, client=None):
    if not project:
        return [], ["Runtime collection requires PFIA_DOCKER_PROJECT; no containers queried."]
    own_client = client is None
    metrics, warnings = [], []
    try:
        if own_client:
            import docker
            # Do not honor DOCKER_HOST: restrict collection to the local engine.
            import os
            client = docker.DockerClient(base_url="npipe:////./pipe/docker_engine" if os.name == "nt" else "unix:///var/run/docker.sock", timeout=3)
        containers = client.containers.list(all=True, filters={"label": f"com.docker.compose.project={project}"})
        for container in containers[:100]:
            name = container.labels.get("com.docker.compose.service")
            if name not in allowed_services:
                continue
            try:
                stats = container.stats(stream=False) if container.status == "running" else {}
                metrics.append(parse_stats(name, container.id, container.attrs, stats))
            except Exception:
                warnings.append(f"Metrics unavailable for {name}; Docker error details withheld.")
    except Exception:
        warnings.append("Local Docker engine unavailable or access denied; deterministic analysis continues.")
    finally:
        if own_client and client is not None:
            client.close()
    return metrics, warnings
