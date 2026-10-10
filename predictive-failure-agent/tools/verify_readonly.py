"""Optional manual live-system evidence, never part of the normal test suite."""
import argparse
import json
import os
from pathlib import Path
from agent.predictive_agent import PredictiveAgent


def main():
    parser = argparse.ArgumentParser(description="PFIA read-only verification. No faults or business writes.")
    parser.add_argument("--runtime", action="store_true", help="Explicitly collect authorized local Compose metrics and one health GET per application service")
    args = parser.parse_args()
    if args.runtime and (os.getenv("PFIA_COLLECT_RUNTIME", "false").lower() != "true" or not os.getenv("PFIA_DOCKER_PROJECT")):
        parser.error("--runtime requires PFIA_COLLECT_RUNTIME=true and PFIA_DOCKER_PROJECT")
    before = {}
    client = None
    if args.runtime:
        import docker
        client = docker.DockerClient(base_url="npipe:////./pipe/docker_engine" if os.name == "nt" else "unix:///var/run/docker.sock", timeout=3)
        before = {c.id: (c.attrs["State"].get("StartedAt"), c.attrs.get("RestartCount")) for c in client.containers.list(all=True, filters={"label": "com.docker.compose.project=" + os.environ["PFIA_DOCKER_PROJECT"]})}
    agent = PredictiveAgent()
    result = agent.analyze(runtime=args.runtime, use_groq=False)
    unchanged = None
    if client:
        after = {c.id: (c.attrs["State"].get("StartedAt"), c.attrs.get("RestartCount")) for c in client.containers.list(all=True, filters={"label": "com.docker.compose.project=" + os.environ["PFIA_DOCKER_PROJECT"]})}
        unchanged = before == after
        client.close()
    evidence = {"verification": "live-system read-only" if args.runtime else "repository static inspection", "timestamp": result["timestamp"], "services": len(result["services"]), "dependency_records": len(result["dependencies"]), "findings": len(result["findings"]), "metrics_count": len(result["metrics"]), "health": result["health"], "container_starts_and_restarts_unchanged": unchanged, "top_risks": result["weak_nodes"][:5], "warnings": result["warnings"], "live_groq_tested": False, "fault_injected": False}
    path = Path(__file__).resolve().parents[1] / "storage/verification.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if k != "top_risks"}, indent=2))
    if unchanged is False:
        raise SystemExit("Container lifecycle changed during observation; investigate external activity.")


if __name__ == "__main__":
    main()
