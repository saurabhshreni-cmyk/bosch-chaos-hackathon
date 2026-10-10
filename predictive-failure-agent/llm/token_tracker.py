class TokenTracker:
    def __init__(self, storage):
        self.storage = storage

    def record(self, model, usage, status, verification="live provider"):
        record = {"model": model, "input_tokens": getattr(usage, "prompt_tokens", 0) or 0, "output_tokens": getattr(usage, "completion_tokens", 0) or 0, "status": status, "verification": verification}
        self.storage.save("llm_usage", record)
        return record

    def totals(self):
        rows = self.storage.read("llm_usage", 10000)
        return {"calls": len(rows), "input_tokens": sum(r["input_tokens"] for r in rows), "output_tokens": sum(r["output_tokens"] for r in rows), "scope": "retained local records; cache hits consume no tokens", "records": rows[:100]}
