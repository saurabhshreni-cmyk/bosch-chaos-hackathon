"""Opt-in, serial GET probes of discovered application health routes only."""
import time
import httpx


def probe(services, metrics, project, client=None):
    # Mappings are obtained from local Docker inspect, never from AI or API input.
    if not project or not metrics:
        return []
    own = client is None
    results = []
    try:
        if own:
            import docker
            import os
            client = docker.DockerClient(base_url="npipe:////./pipe/docker_engine" if os.name == "nt" else "unix:///var/run/docker.sock", timeout=3)
        containers = client.containers.list(filters={"label": f"com.docker.compose.project={project}"})
        with httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as http:
            for container in containers[:100]:
                name = container.labels.get("com.docker.compose.service")
                service = next((s for s in services if s.name == name), None)
                if not service or not service.health_path or not service.health_path.startswith("/"):
                    continue
                ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
                bindings = [binding for values in ports.values() if values for binding in values if binding.get("HostIp") in {"0.0.0.0", "127.0.0.1", ""}]
                if not bindings:
                    continue
                port = int(bindings[0]["HostPort"])
                started = time.monotonic()
                try:
                    response = http.get(f"http://127.0.0.1:{port}{service.health_path}")
                    results.append({"component": name, "status_code": response.status_code, "latency_ms": round((time.monotonic() - started) * 1000, 2), "scope": "application health endpoint; not business recovery proof", "timestamp": time.time()})
                except httpx.HTTPError:
                    results.append({"component": name, "status_code": None, "latency_ms": None, "scope": "health endpoint probe failed", "timestamp": time.time()})
    except Exception:
        return results
    finally:
        if own and client is not None:
            client.close()
    return results
