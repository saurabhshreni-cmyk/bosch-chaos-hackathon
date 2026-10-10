"""All providers below are synthetic, never a live Groq check."""
import json
from types import SimpleNamespace as NS
import pytest
from llm.groq_client import GroqReasoner

EVIDENCE = {"components": ["api"], "findings": [{"id": "synthetic-id", "component": "api", "title": "Synthetic finding"}], "scenarios": []}
VALID = {"hypotheses": [{"component": "api", "evidence_ids": ["synthetic-id"], "hypothesis": "A dependency may slow requests.", "mitigation": "Measure bounded request budgets.", "verification": "Use a disposable environment with automatic recovery."}], "missing_evidence": ["Measured capacity"]}


class FakeProvider:
    def __init__(self, content=None, errors=(), models=None):
        self.content = json.dumps(VALID) if content is None else content
        self.errors = list(errors)
        self.calls = []
        self.models = NS(list=lambda: NS(data=[NS(id=m) for m in (models if models is not None else ["openai/gpt-oss-20b", "openai/gpt-oss-120b"])]))
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return NS(usage=NS(prompt_tokens=23, completion_tokens=17), choices=[NS(finish_reason="stop", message=NS(content=self.content))])


def test_success_strict_schema_cache_and_tokens(store):
    fake = FakeProvider()
    reasoner = GroqReasoner(store, fake)
    assert reasoner.explain(EVIDENCE)["status"] == "available"
    assert fake.calls[0]["response_format"]["json_schema"]["strict"] is True
    assert reasoner.explain(EVIDENCE)["status"] == "cached"
    assert len(fake.calls) == 1
    totals = reasoner.tracker.totals()
    assert totals["input_tokens"] == 23 and totals["output_tokens"] == 17


@pytest.mark.parametrize("content", ["", "not-json", "{}", '{"hypotheses": [], "missing_evidence": [], "score": 99}', json.dumps({"hypotheses": [{**VALID["hypotheses"][0], "component": "unknown"}], "missing_evidence": []}), json.dumps({"hypotheses": [{**VALID["hypotheses"][0], "evidence_ids": ["invented"]}], "missing_evidence": []})])
def test_invalid_or_unfounded_output_rejected(store, content):
    reasoner = GroqReasoner(store, FakeProvider(content))
    result = reasoner.explain(EVIDENCE)
    assert result["narrative"] is None
    assert "rejected" in result["status"]
    assert reasoner.tracker.totals()["calls"] == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_bounded_retry_then_success(store, status):
    error = RuntimeError("synthetic-key-do-not-log")
    error.status_code = status
    delays = []
    fake = FakeProvider(errors=[error])
    reasoner = GroqReasoner(store, fake, sleep=delays.append)
    assert reasoner.explain(EVIDENCE)["status"] == "available"
    assert len(fake.calls) == 2 and delays == [.5]


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_errors_do_not_retry_or_leak(store, status):
    error = RuntimeError("synthetic-key-do-not-log")
    error.status_code = status
    fake = FakeProvider(errors=[error])
    result = GroqReasoner(store, fake).explain(EVIDENCE)
    assert result["narrative"] is None and len(fake.calls) == 1
    assert "synthetic-key" not in str(result)


def test_call_budget_includes_models_and_retries(store, monkeypatch):
    monkeypatch.setenv("LLM_MAX_CALLS_PER_ANALYSIS", "1")
    fake = FakeProvider()
    reasoner = GroqReasoner(store, fake)
    assert reasoner.explain(EVIDENCE)["status"] == "call budget exhausted"
    assert fake.calls == []


def test_unavailable_model(store):
    fake = FakeProvider(models=[])
    assert GroqReasoner(store, fake).explain(EVIDENCE)["status"] == "Configured model unavailable"
    assert fake.calls == []


def test_missing_api_key_keeps_deterministic_path(store):
    assert "not configured" in GroqReasoner(store).explain(EVIDENCE)["status"]


def test_transport_error_sanitized_without_retry(store):
    fake = FakeProvider(errors=[TimeoutError("synthetic-key")])
    result = GroqReasoner(store, fake).explain(EVIDENCE)
    assert "transport error" in result["status"]
    assert "synthetic-key" not in str(result)
    assert len(fake.calls) == 1


def test_reasoning_model_selected_for_complex_analysis(store):
    fake = FakeProvider()
    GroqReasoner(store, fake).explain(EVIDENCE, complex_analysis=True)
    assert fake.calls[0]["model"] == "openai/gpt-oss-120b"


def test_official_sdk_mocked_http_contract(store):
    import httpx
    from groq import Groq
    requests = []
    def transport(request):
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"object": "list", "data": [{"id": "openai/gpt-oss-20b", "object": "model", "created": 1, "owned_by": "synthetic"}]})
        return httpx.Response(200, json={"id": "synthetic-response", "object": "chat.completion", "created": 1, "model": "openai/gpt-oss-20b", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(VALID)}}], "usage": {"prompt_tokens": 23, "completion_tokens": 17, "total_tokens": 40}})
    with Groq(api_key="synthetic-not-a-key", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(transport))) as sdk:
        result = GroqReasoner(store, sdk).explain(EVIDENCE)
    assert result["status"] == "available"
    assert len(requests) == 2
    assert json.loads(requests[1].content)["max_completion_tokens"] == 1024
    assert store.read("llm_usage")[0]["verification"] == "mocked provider"


def test_rate_limit_exhaustion_is_bounded(store):
    error = RuntimeError("synthetic-secret")
    error.status_code = 429
    fake = FakeProvider(errors=[error, error])
    reasoner = GroqReasoner(store, fake, sleep=lambda _: None)
    assert reasoner.explain(EVIDENCE)["narrative"] is None
    assert len(fake.calls) == 2


def test_model_listing_failure_sanitized(store):
    fake = FakeProvider()
    def fail():
        raise RuntimeError("synthetic-secret")
    fake.models.list = fail
    result = GroqReasoner(store, fake).explain(EVIDENCE)
    assert "availability check failed" in result["status"]
    assert "synthetic-secret" not in str(result)


def test_incomplete_response_not_cached(store):
    fake = FakeProvider()
    original = fake.create
    def truncated(**kwargs):
        response = original(**kwargs)
        response.choices[0].finish_reason = "length"
        return response
    fake.chat.completions.create = truncated
    assert "Incomplete" in GroqReasoner(store, fake).explain(EVIDENCE)["status"]
