"""Explicit Docker operations. No model text enters a command or target selector."""
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse
import docker
import httpx
from platform_agents.schemas import digest


WATCHDOG_SCRIPT = r'''
deadline="$1"; shift
command -v timeout >/dev/null || exit 72
timeout 4 docker info >/dev/null 2>&1 || exit 73
for target in "$@"; do
  timeout 4 docker inspect "$target" >/dev/null 2>&1 || exit 74
done
touch /control/armed
while :; do
  now=$(date +%s)
  heartbeat=$(cat /global-control/heartbeat 2>/dev/null)
  case "$heartbeat" in ''|*[!0-9]*) heartbeat=0 ;; esac
  stale=$((now - heartbeat))
  if [ "$now" -ge "$deadline" ] || [ "$stale" -gt 10 ] || [ -f /control/ABORT ] || [ -f /global-control/STOP ]; then
    all_running=1
    for target in "$@"; do
      timeout 4 docker start "$target" >/dev/null 2>&1 || all_running=0
      state=$(timeout 4 docker inspect -f '{{.State.Running}}' "$target" 2>/dev/null)
      [ "$state" = true ] || all_running=0
    done
    if [ "$all_running" = 1 ]; then
      touch /control/infrastructure-restored
      [ -f /control/RELEASE ] && exit 0
    else
      rm -f /control/infrastructure-restored
      echo 'Rollback incomplete; retaining watchdog' >&2
    fi
  fi
  sleep 1
done
'''


class SafetyError(ValueError):
    pass


def validate_probe(probe):
    parsed = urlparse(probe.url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SafetyError("Probes must be local HTTP GETs without credentials, query strings or fragments")
    if not parsed.port:
        raise SafetyError("Probe must specify a published local port")
    return parsed


class DockerAdapter:
    def __init__(self, policy, control_root):
        self.policy = policy
        self.control_root = Path(control_root).resolve()
        # Never honor a remote DOCKER_HOST for operational access.
        self.client = docker.DockerClient(base_url="npipe:////./pipe/docker_engine" if os.name == "nt" else "unix:///var/run/docker.sock", timeout=5)

    def inspect(self, targets, required_components):
        if not self.policy.enabled or not self.policy.project.startswith("pfia-disposable-"):
            raise SafetyError("Execution is disabled or the environment is not disposable")
        compose = Path(self.policy.compose_file).resolve(strict=True)
        if compose.suffix.lower() not in {".yml", ".yaml"}:
            raise SafetyError("Invalid Compose configuration path")
        rows, containers = {}, self.client.containers.list(all=True, filters={"label": f"com.docker.compose.project={self.policy.project}"})
        for container in containers:
            container.reload()
            attrs = container.attrs
            labels = attrs.get("Config", {}).get("Labels", {}) or {}
            name = labels.get("com.docker.compose.service")
            if name not in required_components:
                continue
            if name in rows:
                raise SafetyError("Replicated targets are not supported by the initial adapter")
            files = labels.get("com.docker.compose.project.config_files", "").split(",")
            if labels.get("pfia.disposable") != "true" or not any(Path(f).resolve() == compose for f in files if f):
                raise SafetyError("Disposable label or Compose ownership does not match")
            if not re.fullmatch(r"[a-f0-9]{64}", container.id):
                raise SafetyError("A full immutable Docker ID is required")
            host = attrs.get("HostConfig", {})
            if host.get("Privileged") or host.get("NetworkMode") == "host" or any(m.get("Source") == "/var/run/docker.sock" for m in attrs.get("Mounts", [])):
                raise SafetyError("Privileged, host-network or Docker-socket targets are forbidden")
            if name in targets and any(m.get("Type") in {"volume", "bind"} for m in attrs.get("Mounts", [])):
                raise SafetyError("Targets with persistent volumes or host bind mounts are not supported")
            networks = attrs.get("NetworkSettings", {}).get("Networks", {})
            if not networks or host.get("ExtraHosts"):
                raise SafetyError("Disposable internal networks without host aliases are required")
            network_evidence = {}
            for network_id in networks:
                network = self.client.networks.get(network_id)
                network.reload()
                info = network.attrs
                if info.get("Driver") != "bridge" or not info.get("Internal") or (info.get("Labels") or {}).get("com.docker.compose.project") != self.policy.project:
                    raise SafetyError("All affected services require project-owned internal bridge networks")
                members = info.get("Containers", {})
                if len(members) > 100 or container.id not in members:
                    raise SafetyError("Network membership cannot be verified safely")
                for peer_id in members:
                    if peer_id == container.id:
                        continue
                    peer = self.client.containers.get(peer_id)
                    peer.reload()
                    peer_labels = peer.attrs.get("Config", {}).get("Labels", {}) or {}
                    if peer_labels.get("com.docker.compose.project") != self.policy.project or peer_labels.get("pfia.disposable") != "true":
                        raise SafetyError("Disposable network contains an unauthorized peer")
                network_evidence[network_id] = sorted(members)
            ports = attrs.get("NetworkSettings", {}).get("Ports", {})
            if any(binding.get("HostIp") not in {"127.0.0.1", "::1"} for group in ports.values() if group for binding in group):
                raise SafetyError("Disposable published ports must bind only to loopback")
            state = attrs["State"]
            if state.get("Status") != "running" or state.get("Paused") or state.get("Health", {}).get("Status") == "unhealthy":
                raise SafetyError("All affected services must have a healthy running baseline")
            rows[name] = {"id": container.id, "image": attrs.get("Image"), "started_at": state.get("StartedAt"), "status": state.get("Status"), "ports": ports, "networks": network_evidence, "labels": {k: labels[k] for k in ("com.docker.compose.project", "com.docker.compose.service", "com.docker.compose.project.config_files", "pfia.disposable")}, "health": state.get("Health", {}).get("Status", "not configured")}
        if set(rows) != set(required_components):
            raise SafetyError("Not all affected components exist in the authorized disposable environment")
        for probe in self.policy.probes:
            if probe.component not in required_components:
                continue
            port = validate_probe(probe).port
            bindings = rows[probe.component]["ports"].values()
            if not any(str(port) == binding.get("HostPort") for group in bindings if group for binding in group):
                raise SafetyError("Probe port does not belong to its authorized component")
        return {"containers": rows, "fingerprint": digest({"containers": rows, "compose_hash": digest(compose.read_text())})}

    def probe(self, components):
        observations = []
        for probe in self.policy.probes:
            if probe.component not in components:
                continue
            validate_probe(probe)
            ok = False
            try:
                with httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as client:
                    with client.stream("GET", probe.url) as response:
                        # Bounded response reading, no response bodies retained in evidence/logs.
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            body.extend(chunk[:max(0, 65536 - len(body))])
                            if len(body) >= 65536:
                                break
                        ok = response.status_code == 200 and probe.required_text in body.decode("utf-8", errors="replace")
            except httpx.HTTPError:
                pass
            observations.append({"component": probe.component, "purpose": probe.purpose, "ok": ok, "timestamp": time.time()})
        return observations

    def arm(self, experiment_id, ids, deadline):
        if not ids or any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in ids):
            raise SafetyError("Watchdog requires exact immutable container IDs")
        image = self.client.images.get(self.policy.watchdog_image)  # Never pull an unreviewed image.
        folder = self.control_root / experiment_id
        folder.mkdir(parents=True, exist_ok=False)
        # Docker's atomic name allocation also excludes another PFIA process/database
        # attempting to fault the same project. A failed watchdog blocks new injection.
        # containers.run() implicitly pulls on ImageNotFound; create() does not.
        watchdog = self.client.containers.create(
            image.id,
            name="pfia-watchdog-" + digest(self.policy.project)[:16],
            entrypoint=["sh", "-c", WATCHDOG_SCRIPT, "pfia-watchdog"],
            command=[str(int(deadline)), *ids],
            detach=True,
            network_disabled=True,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            restart_policy={"Name": "unless-stopped"},
            environment={"DOCKER_HOST": "unix:///var/run/docker.sock", "DOCKER_CONTEXT": "", "DOCKER_TLS_VERIFY": ""},
            labels={"pfia.watchdog": experiment_id, "pfia.watchdog.project": self.policy.project},
            volumes={
                "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
                str(folder): {"bind": "/control", "mode": "rw"},
                str(self.control_root): {"bind": "/global-control", "mode": "ro"},
            },
        )
        # Caller persists this ID before the watchdog start request.
        return watchdog.id

    def start_watchdog(self, watchdog_id):
        self.client.containers.get(watchdog_id).start()

    def watchdog_ready(self, experiment_id, watchdog_id):
        watchdog = self.client.containers.get(watchdog_id)
        watchdog.reload()
        return watchdog.status == "running" and (self.control_root / experiment_id / "armed").exists()

    def stop(self, container_id):
        self.client.containers.get(container_id).stop(timeout=1)

    def start(self, container_id):
        self.client.containers.get(container_id).start()

    def states(self, ids):
        result = {}
        for container_id in ids:
            container = self.client.containers.get(container_id)
            container.reload()
            state = container.attrs["State"]
            result[container_id] = {"running": state.get("Running", False), "health": state.get("Health", {}).get("Status", "not configured")}
        return result

    def abort(self, experiment_id):
        folder = self.control_root / experiment_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ABORT").touch()

    def release(self, experiment_id, watchdog_id):
        (self.control_root / experiment_id / "RELEASE").touch()
        # The watchdog must itself observe restored infrastructure and exit.
        watchdog = self.client.containers.get(watchdog_id)
        watchdog.wait(timeout=6)
        watchdog.reload()
        if watchdog.attrs["State"].get("ExitCode") != 0:
            raise SafetyError("Watchdog did not verify rollback; retaining it")
        watchdog.remove()

    def close(self):
        self.client.close()
