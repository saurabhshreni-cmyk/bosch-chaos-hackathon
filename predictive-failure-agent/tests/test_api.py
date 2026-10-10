import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from agent.predictive_agent import PredictiveAgent


@pytest.mark.parametrize("path", ["services", "dependencies", "metrics", "weak-nodes", "findings", "scenarios", "recommendations", "llm-usage", "analysis"])
def test_get_endpoints_static_only(checkout, store, path):
    with TestClient(create_app(PredictiveAgent(checkout, store))) as client:
        response = client.get("/api/" + path)
        assert response.status_code == 200
        assert "synthetic-private-value" not in response.text


def test_analyze_refresh_and_scenario(checkout, store):
    with TestClient(create_app(PredictiveAgent(checkout, store))) as client:
        for path in ["/api/analyze", "/api/analysis/refresh"]:
            response = client.post(path, json={"runtime": False, "use_groq": False})
            assert response.status_code == 200
            assert response.json()["metrics"] == []
        result = client.post("/api/scenarios/evaluate", json={"kind": "traffic", "traffic_multiplier": 5})
        assert result.status_code == 200
        assert "No measured capacity" in result.json()["detail"]
        assert all(not r["executable"] for r in client.get("/api/recommendations").json())


def test_no_execution_or_unvalidated_parameters(checkout, store):
    with TestClient(create_app(PredictiveAgent(checkout, store))) as client:
        assert client.post("/api/execute", json={}).status_code == 404
        assert client.post("/api/analyze", json={"command": "stop"}).status_code == 422
        assert client.post("/api/scenarios/evaluate", json={"kind": "container", "target": "foreign"}).status_code == 422


def test_concurrent_analysis_rejected(checkout, store):
    agent = PredictiveAgent(checkout, store)
    agent.analyze()
    agent.lock.acquire()
    try:
        with TestClient(create_app(agent)) as client:
            assert client.post("/api/analyze", json={}).status_code == 409
            assert client.post("/api/scenarios/evaluate", json={"kind": "traffic"}).status_code == 409
    finally:
        agent.lock.release()


def test_opt_in_cannot_bypass_backend_gate(checkout, store):
    with TestClient(create_app(PredictiveAgent(checkout, store))) as client:
        result = client.post("/api/analyze", json={"runtime": True, "use_groq": True}).json()
        assert result["metrics"] == []
        assert any("disabled" in w.lower() for w in result["warnings"])


def test_docker_initialization_failure_keeps_static_analysis(checkout, store, monkeypatch):
    monkeypatch.setenv("PFIA_COLLECT_RUNTIME", "true")
    monkeypatch.setenv("PFIA_DOCKER_PROJECT", "synthetic-project")
    # The autouse guard raises at the constructor, just as an unavailable engine can.
    with TestClient(create_app(PredictiveAgent(checkout, store))) as client:
        result = client.post("/api/analyze", json={"runtime": True}).json()
        assert len(result["services"]) == 2
        assert result["metrics"] == []
        assert any("engine unavailable" in warning for warning in result["warnings"])
