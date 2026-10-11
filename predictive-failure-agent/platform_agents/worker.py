"""Separate execution/observation process; Docker watchdog survives this process."""
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from agent.predictive_agent import PredictiveAgent
from platform_agents.orchestrator import Platform


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    # Avoid external graph tracing; operational evidence is local only.
    os.environ["LANGSMITH_TRACING"] = "false"
    platform = Platform(PredictiveAgent())
    lock = open(platform.control_root / "worker.lock", "a+b")
    lock.seek(0)
    if os.name == "nt":
        import msvcrt
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        last_scan = 0
        while True:
            platform.tick()
            if platform.policy.enabled and time.time() - last_scan >= 15:
                from monitoring.docker_metrics import collect
                metrics, warnings = collect(set(platform.policy.allowed_services), platform.policy.project)
                incidents = []
                for metric in metrics:
                    platform.agent.storage.save("chaos_metric", {**metric.model_dump(), "project": platform.policy.project})
                    if metric.state != "running" or metric.health == "unhealthy":
                        incidents.append({"id": "unexpected-" + metric.container_id, "component": metric.component, "observed_state": metric.state, "health": metric.health, "timestamp": metric.timestamp, "hypothesis": "Container failure observed; root cause has not been established", "proposed_playbook": "start or restart only after separate authorization and baseline review", "automatic_execution": False})
                platform.store.control("unexpected_incidents", incidents)
                platform.store.control("monitoring_warnings", warnings)
                last_scan = time.time()
            time.sleep(1)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
