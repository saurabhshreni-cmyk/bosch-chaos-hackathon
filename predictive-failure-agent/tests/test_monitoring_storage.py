import time
from types import SimpleNamespace
from monitoring.docker_metrics import parse_stats, collect
from monitoring.metrics_storage import Storage
from llm.cache import cache_key


def test_docker_stats_parse_synthetic():
    attrs = {"State": {"Status": "running", "Health": {"Status": "healthy"}}, "HostConfig": {"Memory": 1000}, "RestartCount": 2}
    stats = {"cpu_stats": {"cpu_usage": {"total_usage": 200}, "system_cpu_usage": 1000, "online_cpus": 2}, "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 500}, "memory_stats": {"usage": 900, "limit": 1000, "stats": {"inactive_file": 100}}, "networks": {"eth0": {"rx_bytes": 12, "tx_bytes": 34}}}
    metric = parse_stats("api", "synthetic", attrs, stats)
    assert metric.cpu_percent == 40
    assert metric.memory_bytes == 800
    assert metric.configured_memory_limit == 1000
    assert metric.network_tx_bytes == 34
    assert metric.restart_count == 2


def test_missing_cpu_delta_is_unknown():
    metric = parse_stats("api", "synthetic", {}, {})
    assert metric.cpu_percent is None
    assert metric.configured_memory_limit is None


def test_collection_filters_project_and_service():
    seen = []
    class Containers:
        def list(self, **kwargs):
            seen.append(kwargs)
            return [SimpleNamespace(labels={"com.docker.compose.service": "foreign"})]
    result, warnings = collect({"api"}, "synthetic-project", SimpleNamespace(containers=Containers()))
    assert result == [] and warnings == []
    assert seen == [{"all": True, "filters": {"label": "com.docker.compose.project=synthetic-project"}}]


def test_no_project_no_query():
    assert collect({"api"}, "")[0] == []


def test_engine_failure_sanitized():
    class Containers:
        def list(self, **kwargs):
            raise RuntimeError("synthetic-secret")
    result, warnings = collect({"api"}, "synthetic", SimpleNamespace(containers=Containers()))
    assert result == []
    assert "synthetic-secret" not in str(warnings)


def test_storage_retention_and_bound(tmp_path):
    store = Storage(tmp_path / "synthetic.sqlite", max_samples=10)
    for i in range(15):
        store.save("metric", {"value": i})
    assert len(store.read("metric")) == 10
    with store.connect() as db:
        db.execute("UPDATE records SET ts=?", (time.time()-8*86400,))
    store.save("metric", {"value": 99})
    assert store.read("metric") == [{"value": 99}]


def test_cache_hash_and_expiry(store):
    key = cache_key("synthetic-model", {"hash": "a"}, {})
    assert key != cache_key("synthetic-model", {"hash": "b"}, {})
    store.cache_set(key, {"ok": True})
    assert store.cache_get(key) == {"ok": True}
    with store.connect() as db:
        db.execute("UPDATE cache SET ts=?", (time.time()-8*86400,))
    assert store.cache_get(key) is None
