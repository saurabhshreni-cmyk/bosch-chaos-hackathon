import json
import os
import time
from pydantic import ValidationError
from agent.schemas import Narrative
from llm.cache import cache_key
from llm.prompts import SYSTEM
from llm.token_tracker import TokenTracker


class GroqReasoner:
    def __init__(self, storage, client=None, sleep=time.sleep):
        self.storage = storage
        self.client = client
        self.verification = "mocked provider" if client is not None else "live provider"
        self.sleep = sleep
        self.tracker = TokenTracker(storage)
        self.fast = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
        self.reasoning = os.getenv("GROQ_REASONING_MODEL", "openai/gpt-oss-120b")
        self.max_calls = max(0, min(int(os.getenv("LLM_MAX_CALLS_PER_ANALYSIS", "15")), 15))
        self.max_tokens = max(128, min(int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1024")), 4096))
        self.temperature = min(1, max(0, float(os.getenv("LLM_TEMPERATURE", "0.1"))))
        self.attempts = 0
        self.available_models = None

    def reset_budget(self):
        self.attempts = 0

    def explain(self, evidence, complex_analysis=False):
        model = self.reasoning if complex_analysis else self.fast
        key = cache_key(model, evidence, [self.temperature, self.max_tokens])
        cached = self.storage.cache_get(key)
        if cached is not None:
            return {"status": "cached", "model": model, "narrative": cached, "classification": "unverified AI hypotheses"}
        if self.max_calls <= self.attempts:
            return {"status": "call budget exhausted", "narrative": None}
        if self.client is None:
            if not os.getenv("GROQ_API_KEY"):
                return {"status": "GROQ_API_KEY not configured; deterministic analysis retained", "narrative": None}
            try:
                from groq import Groq
                self.client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=15, max_retries=0)
            except Exception:
                return {"status": "Groq client initialization failed; details withheld", "narrative": None}
        # One API attempt includes model listing. SDK retries disabled so budgets are explicit.
        if self.available_models is None:
            try:
                self.attempts += 1
                self.available_models = {m.id for m in self.client.models.list().data}
            except Exception:
                return {"status": "Model availability check failed; details withheld", "narrative": None}
        if model not in self.available_models:
            return {"status": "Configured model unavailable", "narrative": None}
        schema = Narrative.model_json_schema()
        strict = model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
        response_format = {"type": "json_schema", "json_schema": {"name": "reliability_hypotheses", "strict": True, "schema": schema}} if strict else {"type": "json_object"}
        payload = json.dumps(evidence, sort_keys=True)
        if len(payload) > 24000:
            return {"status": "Evidence budget exceeded; deterministic analysis retained", "narrative": None}
        for attempt in range(2):
            if self.attempts >= self.max_calls:
                break
            self.attempts += 1
            try:
                response = self.client.chat.completions.create(model=model, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": payload + "\nSchema: " + json.dumps(schema)}], response_format=response_format, max_completion_tokens=self.max_tokens, temperature=self.temperature)
                # Record actual returned usage even if the model output fails validation.
                self.tracker.record(model, response.usage, "response received; validation pending", self.verification)
                if response.choices[0].finish_reason != "stop":
                    return {"status": "Incomplete model response rejected", "narrative": None}
                narrative = Narrative.model_validate_json(response.choices[0].message.content, strict=True)
                known = {f["id"]: f["component"] for f in evidence["findings"]}
                for hypothesis in narrative.hypotheses:
                    if hypothesis.component not in evidence["components"] or not hypothesis.evidence_ids or any(known.get(fid) != hypothesis.component for fid in hypothesis.evidence_ids):
                        raise ValueError("Unsupported evidence reference")
                result = narrative.model_dump()
                self.storage.cache_set(key, result)
                return {"status": "available", "model": model, "narrative": result, "classification": "unverified AI hypotheses"}
            except (ValidationError, ValueError, IndexError, AttributeError, TypeError):
                return {"status": "Invalid or unsupported model response rejected", "narrative": None}
            except Exception as error:
                code = getattr(error, "status_code", None)
                if code in {429, 500, 502, 503, 504} and attempt == 0 and self.attempts < self.max_calls:
                    self.sleep(.5 * 2**attempt)
                    continue
                return {"status": f"Groq unavailable ({code if isinstance(code, int) else 'transport error'}); details withheld", "narrative": None}
        return {"status": "call budget exhausted", "narrative": None}
