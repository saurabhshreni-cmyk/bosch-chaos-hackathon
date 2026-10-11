import hashlib
import json
import os
import threading
import time
from pathlib import Path
from agent.schemas import ScenarioRequest
from discovery.service_discovery import discover
from discovery.code_analyzer import analyze_code
from discovery.dependency_graph import build_graph, graph_metrics
from monitoring.docker_metrics import collect
from monitoring.health_checks import probe
from monitoring.metrics_storage import Storage
from analysis.risk_scoring import score
from analysis.bottleneck_detector import detect
from analysis.scenario_engine import evaluate
from agent.reasoning_engine import recommendations
from llm.groq_client import GroqReasoner
from llm.prompts import compact_evidence


class PredictiveAgent:
    def __init__(self, root=None, storage=None):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.storage = storage or Storage(Path(__file__).resolve().parents[1] / "storage/pfia.sqlite3", os.getenv("PFIA_RETENTION_DAYS", 7), os.getenv("PFIA_MAX_SAMPLES", 10000))
        self.lock = threading.Lock()
        self.services = []
        self.graph = None
        self.metrics = []
        self.latest = None
        self.reasoner = GroqReasoner(self.storage)

    def analyze(self, runtime=False, use_groq=False):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("An analysis is already running")
        try:
            services, deps, warnings = discover(self.root)
            findings = analyze_code(self.root, services)
            graph = build_graph(services, deps)
            metrics, health = [], []
            if runtime:
                if os.getenv("PFIA_COLLECT_RUNTIME", "false").lower() != "true":
                    warnings.append("Runtime collection disabled by PFIA_COLLECT_RUNTIME.")
                else:
                    project = os.getenv("PFIA_DOCKER_PROJECT", "")
                    metrics, runtime_warnings = collect({s.name for s in services}, project)
                    warnings.extend(runtime_warnings)
                    health = probe(services, metrics, project)
                    if metrics and not health:
                        warnings.append("No application health probes were obtained; published ports, routes or Docker access may be unavailable.")
                    for metric in metrics:
                        self.storage.save("metric", metric.model_dump())
                    for row in health:
                        self.storage.save("health", row)
            risks = score(services, graph, findings, metrics, self._weights())
            scenarios = []
            for kind in ("traffic", "database", "broker", "network", "resource", "host"):
                try:
                    scenarios.append(evaluate(ScenarioRequest(kind=kind), services, graph, metrics))
                except ValueError:
                    warnings.append(f"{kind} scenario unavailable: required dependency not discovered.")
            fingerprint = hashlib.sha256()
            paths = {"src/docker-compose.yml", "chaos-scripts/dependency-overlay.json"} | {p for s in services for p in s.code_paths}
            for path in sorted(paths):
                file = self.root / path
                if file.exists():
                    fingerprint.update(path.encode())
                    fingerprint.update(file.read_bytes())
            ai = []
            if use_groq and os.getenv("PFIA_ENABLE_GROQ", "false").lower() == "true":
                evidence = compact_evidence(services, findings, scenarios, deps)
                evidence["configuration_hash"] = fingerprint.hexdigest()
                self.reasoner.reset_budget()
                ai = [self.reasoner.explain(evidence), self.reasoner.explain(evidence, complex_analysis=True)]
            elif use_groq:
                warnings.append("Groq disabled by PFIA_ENABLE_GROQ; deterministic results retained.")
            result = {"timestamp": time.time(), "configuration_hash": fingerprint.hexdigest(), "services": [s.model_dump() for s in services], "dependencies": [d.model_dump() for d in deps], "graph_metrics": graph_metrics(graph), "metrics": [m.model_dump() for m in metrics], "health": health, "weak_nodes": [r.model_dump() for r in risks], "findings": [f.model_dump() for f in findings], "scenarios": scenarios, "recommendations": recommendations(findings, risks), "bottlenecks": detect(metrics), "ai_insights": ai, "warnings": warnings, "limitations": ["Scores are relative engineering indicators, not failure probabilities.", "Static analysis is conservative C# lexical inspection, not whole-program verification.", "Queue depth, database query/pool telemetry, worker capacity and request error rates are not collected without dedicated instrumentation.", "Project references establish configured build inputs, not running image provenance or runtime call reachability.", "No fault was injected; no recovery was verified by this agent."]}
            # Recorded recovery evidence supplements, rather than erases, static weaknesses.
            result["experiment_feedback"] = self.storage.read("experiment_feedback", 100)
            for risk in result["weak_nodes"]:
                relevant = [row for row in result["experiment_feedback"] if row.get("configuration_hash") == result["configuration_hash"] and risk["component"] in row.get("components", [])]
                adjustment = max((row.get("risk_score_adjustment", 0) for row in relevant), default=0)
                # At most five evidence-derived points, never an LLM score or cumulative inflation.
                adjustment = max(0, min(5, adjustment))
                risk["score"] = min(100, risk["score"] + adjustment)
                risk["experiment_evidence"] = {"matching_runs": len(relevant), "verified_functional_recoveries": sum(row.get("functional_recovery_verified", False) for row in relevant), "score_adjustment": adjustment, "confidence": "Recorded disposable-environment observations only" if relevant else "No matching experiment evidence"}
            result["weak_nodes"].sort(key=lambda row: (-row["score"], row["component"]))
            scores = {row["component"]: row["score"] for row in result["weak_nodes"]}
            for recommendation in result["recommendations"]:
                recommendation["risk_score"] = scores[recommendation["component"]]
            result["limitations"][-1] = "Analysis itself injects no faults. Recovery evidence, when present, is recorded separately in experiment_feedback."
            self.storage.save("analysis", result)
            self.services, self.graph, self.metrics, self.latest = services, graph, metrics, result
            return result
        finally:
            self.lock.release()

    def _weights(self):
        path = Path(__file__).resolve().parents[1] / "risk-weights.json"
        return json.loads(path.read_text()) if path.exists() else None

    def scenario(self, request):
        if self.graph is None:
            self.analyze()
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("An analysis is already running")
        try:
            result = evaluate(request, self.services, self.graph, self.metrics)
            self.storage.save("scenario", result)
            return result
        finally:
            self.lock.release()
