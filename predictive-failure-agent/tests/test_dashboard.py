"""Streamlit application integration using synthetic in-memory API responses."""
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from streamlit.testing.v1 import AppTest
from agent.predictive_agent import PredictiveAgent
from agent.schemas import ScenarioRequest


def test_dashboard_renders_and_analyze_click(checkout, store, monkeypatch):
    agent = PredictiveAgent(checkout, store)
    snapshot = agent.analyze()
    calls = []
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            body = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "records": []} if url.endswith("llm-usage") else snapshot
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)
        def post(self, url, json):
            calls.append((url, json))
            body = agent.scenario(ScenarioRequest(**json)) if url.endswith("scenarios/evaluate") else snapshot
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run(timeout=20)
    assert not app.exception
    assert len(app.tabs) == 6
    assert app.metric[0].value == "2"
    next(button for button in app.button if button.label == "Analyze Application").click().run(timeout=20)
    assert not app.exception
    assert calls[0][0].endswith("/api/analyze")
    assert calls[0][1] == {"runtime": False, "use_groq": False}
    next(button for button in app.button if button.label == "Evaluate without injecting faults").click().run(timeout=20)
    assert not app.exception
    assert calls[-1][0].endswith("/api/scenarios/evaluate")


@pytest.mark.parametrize("page", ["Chaos Engineering", "Self-Healing", "Agent Collaboration", "Experiment History"])
def test_platform_pages_use_recorded_api_data(checkout, store, monkeypatch, page):
    snapshot = PredictiveAgent(checkout, store).analyze()
    status = {"analysis": "available", "chaos": "execution disabled", "supported_faults": ["container_stop"], "unsupported_faults": ["network_latency"], "timeline": []}
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            if url.endswith("/api/agents/status"):
                body = status
            elif url.endswith("/api/chaos/recommendations"):
                body = snapshot["recommendations"]
            elif url.endswith("/api/services"):
                body = snapshot["services"]
            elif url.endswith("/api/analysis") or "/api/metrics?" in url:
                body = snapshot
            elif url.endswith("/api/llm-usage"):
                body = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "records": []}
            else:
                body = []
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: body)
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run(timeout=20)
    next(r for r in app.radio if r.label == "Platform page").set_value(page).run(timeout=20)
    assert not app.exception
    assert any(title.value == page for title in app.title)
