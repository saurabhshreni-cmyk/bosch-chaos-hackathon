from pathlib import Path
import networkx as nx
import pytest
from pydantic import ValidationError
from agent.schemas import Dependency, Evidence, Metric, ScenarioRequest
from discovery.service_discovery import discover
from discovery.code_analyzer import analyze_code
from discovery.dependency_graph import build_graph, graph_metrics
from analysis.cascade_analysis import cascade
from analysis.scenario_engine import evaluate
from analysis.risk_scoring import score
from analysis.bottleneck_detector import detect


def test_discover_synthetic_names_not_secret_values(checkout):
    services, edges, warnings = discover(checkout)
    assert len(services) == 2
    assert services[0].environment_names == ["SECRET_TOKEN"]
    assert services[0].health_path == "/hc"
    assert any(e.kind == "database" and e.target == "sqlserver" for e in edges)
    assert warnings == ["api: unresolved startup target missing"]
    assert "synthetic-private-value" not in str([s.model_dump() for s in services]) + str(edges)


def test_external_source_path_not_scanned(checkout):
    file = checkout / "src/docker-compose.yml"
    file.write_text('services:\n  escape:\n    build:\n      context: ../../..\n      dockerfile: private/Dockerfile\n')
    services, _, _ = discover(checkout)
    assert services[0].code_paths == []


def test_local_project_reference_discovered(checkout):
    library = checkout / "src/Shared"
    library.mkdir()
    (library / "Shared.csproj").write_text('<Project><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup></Project>')
    (library / "Client.cs").write_text('class Client {}')
    (checkout / "src/Api/Api.csproj").write_text('<Project><ItemGroup><ProjectReference Include="..\\Shared\\Shared.csproj" /></ItemGroup></Project>')
    services, _, _ = discover(checkout)
    api = services[0]
    assert "src/Shared/Client.cs" in api.code_paths
    assert api.runtime == ".NET net10.0"


def test_static_source_locations_and_hypothesis(checkout):
    services, _, _ = discover(checkout)
    findings = analyze_code(checkout, services)
    timeout = next(f for f in findings if "HTTP timeout" in f.title)
    assert timeout.evidence[0].line == 1
    assert timeout.status == "evidence-supported hypothesis"
    assert any("Immediate retries" in f.title for f in findings)


def test_explicit_timeout_suppresses_timeout_finding(checkout):
    path = checkout / "src/Api/Program.cs"
    path.write_text(path.read_text() + "\nhttpClient.Timeout = TimeSpan.FromSeconds(5);")
    services, _, _ = discover(checkout)
    assert not any("HTTP timeout" in f.title for f in analyze_code(checkout, services))


def test_graph_direction_and_centrality(topology):
    graph = build_graph(*topology)
    result = graph_metrics(graph)
    assert result["sqlserver"]["affected_dependents"] == ["api", "web"]
    assert result["web"]["affected_dependents"] == []
    assert result["api"]["betweenness"] > 0
    assert not graph.has_edge("web", "rabbitmq")
    assert not graph.has_edge("web", "logserver")
    assert result["web"]["dependencies_reachable"] == 3


def test_unknown_edges_are_not_invented(topology):
    services, edges = topology
    edges.append(Dependency(source="ghost", target="api", kind="http", confidence="medium", evidence=Evidence(path="synthetic", line=1, description="ambiguous"), detail="unresolved"))
    assert "ghost" not in build_graph(services, edges)


def test_cascade_reverse_path(topology):
    result = cascade(build_graph(*topology), "sqlserver")
    assert next(r for r in result if r["component"] == "web")["path"] == ["sqlserver", "api", "web"]


def test_cascade_unknown_rejected(topology):
    with pytest.raises(ValueError):
        cascade(build_graph(*topology), "ghost")


@pytest.mark.parametrize("kind", ["traffic", "database", "broker", "network", "resource", "cascade", "container", "host"])
def test_scenarios_are_hypothetical(topology, kind):
    target = {"database": "sqlserver", "broker": "rabbitmq", "cascade": "api", "container": "api"}.get(kind)
    result = evaluate(ScenarioRequest(kind=kind, target=target), topology[0], build_graph(*topology), [])
    assert result["evidence_class"] == "hypothetical analysis"
    assert "No fault" in result["assumptions"][0]


@pytest.mark.parametrize("body", [{"kind": "shell"}, {"kind": "traffic", "traffic_multiplier": 100}, {"kind": "network", "latency_ms": -1}, {"kind": "network", "packet_loss_percent": 101}, {"kind": "resource", "command": "stop"}])
def test_invalid_scenario_parameters_rejected(body):
    with pytest.raises(ValidationError):
        ScenarioRequest(**body)


@pytest.mark.parametrize("kind,target", [("cascade", None), ("container", "ghost"), ("database", "api"), ("broker", "api")])
def test_invalid_targets_rejected(topology, kind, target):
    with pytest.raises(ValueError):
        evaluate(ScenarioRequest(kind=kind, target=target), topology[0], build_graph(*topology), [])


def test_missing_metrics_not_fabricated(topology):
    risks = score(topology[0], build_graph(*topology), [], [])
    assert all(r.evidence_coverage == .8 for r in risks)
    assert all("resource_pressure" not in r.factors for r in risks)
    assert all("Runtime metrics and historical health" in r.missing_evidence for r in risks)
    assert all(0 <= r.score <= 100 for r in risks)
    assert risks[0].component in {"rabbitmq", "sqlserver"}


def test_weight_validation(topology):
    with pytest.raises(ValueError):
        score(topology[0], build_graph(*topology), [], [], {"criticality": 100})


def test_empty_weights_not_silently_replaced(topology):
    with pytest.raises(ValueError):
        score(topology[0], build_graph(*topology), [], [], {})


def test_targeted_resource_scenario_uses_observations(topology):
    metric = Metric(component="api", container_id="synthetic", timestamp=1, state="running", health="unknown", memory_bytes=123)
    result = evaluate(ScenarioRequest(kind="resource", target="api"), topology[0], build_graph(*topology), [metric])
    assert len(result["impacts"]) == 1
    assert result["impacts"][0]["observed_memory_bytes"] == 123
    assert result["impacts"][0]["observed_cpu_percent_one_core"] is None


def test_memory_pressure_needs_configured_limit():
    metric = Metric(component="api", container_id="synthetic", timestamp=1, state="running", health="unknown", cpu_percent=90, memory_bytes=900, stats_memory_limit=1000)
    flags = detect([metric])
    assert len(flags) == 1
    assert "not necessarily saturation" in flags[0]["observation"]
    metric.configured_memory_limit = 1000
    assert len(detect([metric])) == 2


def test_real_checkout_static_inspection_only():
    """Repository integration: real config, no Docker/provider access."""
    root = Path(__file__).resolve().parents[2]
    services, edges, warnings = discover(root)
    assert len(services) == 13
    assert any(e.source == "webapp" and e.kind == "http" for e in edges)
    findings = analyze_code(root, services)
    assert any("event publication divergence" in f.title for f in findings)
    assert not warnings
