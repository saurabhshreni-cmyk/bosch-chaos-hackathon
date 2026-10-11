"""Unit tests of the real adapter with a mocked Docker SDK and synthetic probes."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import docker
import httpx
import pytest
from platform_agents.schemas import Policy, Probe
from platform_agents.docker_adapter import DockerAdapter, SafetyError, WATCHDOG_SCRIPT


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {api: {image: synthetic-only}}")
    policy = Policy(enabled=True, project="pfia-disposable-fixture", compose_file=str(compose), allowed_services=["api"], watchdog_verified=True, probes=[Probe(component="api", url="http://127.0.0.1:8800/health", required_text="READY", purpose="functionality")])
    attrs = {"Config": {"Labels": {"com.docker.compose.project": policy.project, "com.docker.compose.service": "api", "com.docker.compose.project.config_files": str(compose), "pfia.disposable": "true"}}, "State": {"Status": "running", "Running": True, "StartedAt": "synthetic-start", "Health": {"Status": "healthy"}}, "HostConfig": {}, "Mounts": [], "Image": "synthetic-image", "NetworkSettings": {"Ports": {"80/tcp": [{"HostPort": "8800"}]}}}
    target = NS(id="a" * 64, attrs=attrs, reload=lambda: None)
    client = MagicMock()
    client.containers.list.return_value = [target]
    target.attrs["NetworkSettings"]["Ports"]["80/tcp"][0]["HostIp"] = "127.0.0.1"
    target.attrs["NetworkSettings"]["Networks"] = {"synthetic-network": {}}
    client.networks.get.return_value.attrs = {"Driver": "bridge", "Internal": True, "Labels": {"com.docker.compose.project": policy.project}, "Containers": {target.id: {}}}
    monkeypatch.setattr(docker, "DockerClient", lambda **kwargs: client)
    control = tmp_path / "control"
    control.mkdir()
    result = DockerAdapter(policy, control)
    return result, client, target


def test_actual_adapter_ownership_and_compose_change_fingerprint(adapter):
    actual, client, target = adapter
    first = actual.inspect(["api"], {"api"})
    assert first["containers"]["api"]["id"] == "a" * 64
    client.containers.list.assert_called_once_with(all=True, filters={"label": "com.docker.compose.project=pfia-disposable-fixture"})
    with open(actual.policy.compose_file, "a") as file:
        file.write("\n# configuration changed")
    assert actual.inspect(["api"], {"api"})["fingerprint"] != first["fingerprint"]


@pytest.mark.parametrize("unsafe", ["label", "compose", "replica", "privileged", "host", "socket", "volume", "bind", "stopped", "unhealthy", "probe_port", "immutable_id", "public_port", "external_network", "foreign_network", "foreign_peer", "host_alias"])
def test_actual_adapter_rejects_unsafe_target(adapter, unsafe):
    actual, client, target = adapter
    if unsafe == "label":
        target.attrs["Config"]["Labels"]["pfia.disposable"] = "false"
    elif unsafe == "compose":
        target.attrs["Config"]["Labels"]["com.docker.compose.project.config_files"] = "unowned.yml"
    elif unsafe == "replica":
        client.containers.list.return_value = [target, target]
    elif unsafe == "privileged":
        target.attrs["HostConfig"]["Privileged"] = True
    elif unsafe == "host":
        target.attrs["HostConfig"]["NetworkMode"] = "host"
    elif unsafe in {"socket", "volume", "bind"}:
        target.attrs["Mounts"] = [{"Type": "bind" if unsafe != "volume" else "volume", "Source": "/var/run/docker.sock" if unsafe == "socket" else "/synthetic/data"}]
    elif unsafe == "stopped":
        target.attrs["State"]["Status"] = "exited"
    elif unsafe == "unhealthy":
        target.attrs["State"]["Health"]["Status"] = "unhealthy"
    elif unsafe == "probe_port":
        actual.policy.probes[0].url = "http://localhost:9999/health"
    elif unsafe == "immutable_id":
        target.id = "short"
    elif unsafe == "public_port":
        target.attrs["NetworkSettings"]["Ports"]["80/tcp"][0]["HostIp"] = "0.0.0.0"
    elif unsafe == "external_network":
        client.networks.get.return_value.attrs["Internal"] = False
    elif unsafe == "foreign_network":
        client.networks.get.return_value.attrs["Labels"]["com.docker.compose.project"] = "src"
    elif unsafe == "foreign_peer":
        client.networks.get.return_value.attrs["Containers"]["foreign-id"] = {}
        client.containers.get.return_value.attrs = {"Config": {"Labels": {"com.docker.compose.project": "src"}}}
    elif unsafe == "host_alias":
        target.attrs["HostConfig"]["ExtraHosts"] = ["production:host-gateway"]
    with pytest.raises(SafetyError):
        actual.inspect(["api"], {"api"})


def test_watchdog_uses_fixed_script_hardened_container_and_existing_image(adapter):
    actual, client, target = adapter
    client.images.get.return_value.id = "sha256:" + "c" * 64
    client.containers.create.return_value.id = "watchdog-fixture"
    value = actual.arm("fixture-id", [target.id], 1234)
    assert value == "watchdog-fixture"
    client.images.get.assert_called_once_with("docker:cli")
    args, kwargs = client.containers.create.call_args
    assert args[0] == "sha256:" + "c" * 64
    assert kwargs["network_disabled"] and kwargs["read_only"]
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["entrypoint"] == ["sh", "-c", WATCHDOG_SCRIPT, "pfia-watchdog"]
    assert kwargs["command"] == ["1234", "a" * 64]
    assert kwargs["restart_policy"] == {"Name": "unless-stopped"}
    assert kwargs["name"].startswith("pfia-watchdog-")
    assert kwargs["environment"]["DOCKER_HOST"] == "unix:///var/run/docker.sock"
    client.containers.run.assert_not_called()
    client.images.pull.assert_not_called()


def test_exact_lifecycle_operations_and_failed_watchdog_is_retained(adapter):
    actual, client, target = adapter
    actual.stop(target.id)
    client.containers.get.assert_called_with(target.id)
    client.containers.get.return_value.stop.assert_called_once_with(timeout=1)
    actual.start(target.id)
    client.containers.get.return_value.start.assert_called_once_with()
    (actual.control_root / "fixture-id").mkdir()
    client.containers.get.return_value.attrs = {"State": {"ExitCode": 1}}
    with pytest.raises(SafetyError):
        actual.release("fixture-id", "watchdog-fixture")
    client.containers.get.return_value.remove.assert_not_called()


@pytest.mark.parametrize("status,body,ok", [(200, "READY", True), (200, "offline", False), (500, "READY", False), (302, "READY", False)])
def test_functional_probe_status_and_required_content(adapter, monkeypatch, status, body, ok):
    actual, client, target = adapter
    original = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs))
    rows = actual.probe({"api"})
    assert rows[0]["ok"] is ok
    assert body not in str(rows)
