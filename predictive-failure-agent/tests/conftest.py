"""Synthetic fixtures. Automated tests must not access Docker or real providers."""
import socket
import threading
from pathlib import Path
import pytest
from agent.schemas import Dependency, Evidence, Service
from monitoring.metrics_storage import Storage


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original_connect = socket.socket.connect
    original_pair = socket.socketpair
    internal = threading.local()
    def pair(*args, **kwargs):
        # Windows implements asyncio's internal wakeup socketpair over loopback.
        internal.socketpair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            internal.socketpair = False
    def forbidden(sock, address):
        if getattr(internal, "socketpair", False):
            return original_connect(sock, address)
        raise AssertionError("Real network access forbidden in PFIA automated tests")
    monkeypatch.setattr(socket, "socketpair", pair)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    import docker
    monkeypatch.setattr(docker, "DockerClient", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Real Docker access forbidden in automated tests")))
    monkeypatch.setenv("PFIA_COLLECT_RUNTIME", "false")
    monkeypatch.setenv("PFIA_ENABLE_GROQ", "false")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


@pytest.fixture
def store(tmp_path):
    return Storage(tmp_path / "synthetic.sqlite3")


@pytest.fixture
def topology():
    services = [Service(name=n, role="application", runtime="synthetic") for n in ("web", "api", "sqlserver", "rabbitmq", "logserver")]
    evidence = Evidence(path="synthetic.yml", line=1, description="Synthetic fixture")
    dependencies = [Dependency(source=s, target=t, kind=k, confidence="high", evidence=evidence, detail="Synthetic fixture") for s, t, k in [("web", "api", "http"), ("api", "sqlserver", "database"), ("api", "rabbitmq", "broker"), ("web", "logserver", "logging"), ("web", "rabbitmq", "startup")]]
    return services, dependencies


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "synthetic-repo"
    (root / "src/Api").mkdir(parents=True)
    (root / "src/docker-compose.yml").write_text('services:\n  api:\n    build:\n      context: .\n      dockerfile: Api/Dockerfile\n    environment:\n      - SECRET_TOKEN=synthetic-private-value\n    depends_on:\n      sqlserver: {}\n      missing: {}\n  sqlserver:\n    image: synthetic/sql\n')
    (root / "src/Api/Program.cs").write_text('builder.Services.AddHttpClient<IApi, Api>();\nbuilder.Services.AddHealthChecks();\napp.UseHealthChecks("/hc");\nvar retry = Policy.RetryAsync(5);\n')
    (root / "src/Api/appsettings.Production.json").write_text('{"ConnectionStrings":{"Database":"Server=sqlserver;Password=synthetic-private-value"}}')
    return root
