import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from agent.predictive_agent import PredictiveAgent
from agent.schemas import AnalyzeRequest, ScenarioRequest

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def create_app(agent=None):
    async def sampler(instance):
        interval = max(15, min(int(os.getenv("PFIA_SAMPLE_INTERVAL", "60")), 3600))
        while True:
            await asyncio.sleep(interval)
            try:
                await asyncio.to_thread(instance.analyze, True, False)
            except (RuntimeError, OSError, ValueError):
                pass  # Last successful evidence remains available; requests expose errors.

    @asynccontextmanager
    async def lifespan(app):
        app.state.agent = agent or PredictiveAgent()
        task = asyncio.create_task(sampler(app.state.agent)) if os.getenv("PFIA_COLLECT_RUNTIME", "false").lower() == "true" else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="PFIA Three-Agent Platform", version="2.0.0", lifespan=lifespan, description="Read-only analysis plus explicitly approved disposable-environment experiments. Execution disabled by default.")
    from platform_agents.api import router
    app.include_router(router)

    def instance(request: Request):
        return request.app.state.agent

    def snapshot(request):
        current = instance(request)
        if current.latest is None:
            try:
                return current.analyze()
            except RuntimeError:
                raise HTTPException(409, "Analysis already running")
        return current.latest

    @app.get("/api/services")
    def services(request: Request):
        return snapshot(request)["services"]

    @app.get("/api/dependencies")
    def dependencies(request: Request):
        data = snapshot(request)
        return {"direction": "consumer -> dependency", "edges": data["dependencies"], "metrics": data["graph_metrics"]}

    @app.get("/api/metrics")
    def metrics(request: Request, limit: int = 100):
        data = snapshot(request)
        return {"current": data["metrics"], "health": data["health"], "history": instance(request).storage.read("metric", limit), "warnings": data["warnings"]}

    @app.get("/api/weak-nodes")
    def weak_nodes(request: Request):
        return snapshot(request)["weak_nodes"]

    @app.get("/api/findings")
    def findings(request: Request):
        return snapshot(request)["findings"]

    @app.get("/api/scenarios")
    def scenarios(request: Request):
        return snapshot(request)["scenarios"]

    @app.get("/api/recommendations")
    def recommendations(request: Request):
        return snapshot(request)["recommendations"]

    @app.get("/api/llm-usage")
    def usage(request: Request):
        return instance(request).reasoner.tracker.totals()

    @app.get("/api/analysis")
    def analysis(request: Request):
        return snapshot(request)

    @app.post("/api/analyze")
    @app.post("/api/analysis/refresh")
    def analyze(body: AnalyzeRequest, request: Request):
        try:
            return instance(request).analyze(body.runtime, body.use_groq)
        except RuntimeError:
            raise HTTPException(409, "Analysis already running")
        except (OSError, ValueError):
            raise HTTPException(422, "Repository or PFIA configuration cannot be analyzed; check the local setup")

    @app.post("/api/scenarios/evaluate")
    def evaluate(body: ScenarioRequest, request: Request):
        try:
            return instance(request).scenario(body)
        except ValueError as error:
            raise HTTPException(422, str(error))
        except RuntimeError:
            raise HTTPException(409, "Analysis already running")

    return app


app = create_app()
