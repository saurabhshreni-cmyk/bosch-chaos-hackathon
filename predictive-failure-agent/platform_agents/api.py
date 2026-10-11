import hashlib
import hmac
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from platform_agents.schemas import PlanRequest, ApprovalRequest
from platform_agents.orchestrator import Platform
from platform_agents.state_store import Conflict
from platform_agents.docker_adapter import SafetyError


router = APIRouter()


def platform(request: Request):
    if not hasattr(request.app.state, "platform"):
        request.app.state.platform = Platform(request.app.state.agent)
    return request.app.state.platform


def operator(request: Request):
    expected = os.getenv("PFIA_OPERATOR_TOKEN", "")
    supplied = request.headers.get("authorization", "")
    if len(expected) < 32:
        raise HTTPException(503, "Operation authorization is not configured; set a local operator token of at least 32 characters")
    if not supplied.startswith("Bearer ") or not hmac.compare_digest(supplied[7:].encode(), expected.encode()):
        raise HTTPException(401, "Operation authorization required")
    # Store an identifier, never the operator credential.
    return "local-operator-" + hashlib.sha256(expected.encode()).hexdigest()[:12]


def action(function):
    try:
        return function()
    except KeyError:
        raise HTTPException(404, "Experiment not found")
    except (SafetyError, Conflict) as error:
        raise HTTPException(409, str(error))
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(409, "Operation could not be validated; check policy and local service availability")
    except Exception:
        raise HTTPException(503, "Infrastructure unavailable; details withheld")


@router.get("/api/chaos/recommendations")
def recommendations(request: Request):
    return action(lambda: platform(request).chaos.recommendations())


@router.get("/api/chaos/experiments")
def experiments(request: Request):
    return platform(request).store.list()


@router.post("/api/chaos/experiments/plan")
def plan(body: PlanRequest, request: Request, identity=Depends(operator)):
    from platform_agents.workflow import plan as workflow_plan
    return action(lambda: workflow_plan(platform(request), body))


@router.post("/api/chaos/experiments/{experiment_id}/approve")
def approve(experiment_id: str, body: ApprovalRequest, request: Request, identity=Depends(operator)):
    return action(lambda: platform(request).approve(experiment_id, body, identity))


@router.post("/api/chaos/experiments/{experiment_id}/execute")
def execute(experiment_id: str, request: Request, identity=Depends(operator)):
    return action(lambda: platform(request).execute(experiment_id))


@router.post("/api/chaos/experiments/{experiment_id}/reject")
def reject(experiment_id: str, request: Request, identity=Depends(operator)):
    return action(lambda: platform(request).reject(experiment_id))


@router.post("/api/chaos/experiments/{experiment_id}/abort")
def abort(experiment_id: str, request: Request, identity=Depends(operator)):
    return action(lambda: platform(request).abort(experiment_id))


@router.get("/api/chaos/experiments/{experiment_id}/status")
def status(experiment_id: str, request: Request):
    return action(lambda: {"experiment": platform(request).store.get(experiment_id), "timeline": platform(request).store.events(experiment_id)})


@router.get("/api/healing/incidents")
def incidents(request: Request):
    current = platform(request)
    return [{"id": e.id, "state": e.state, "incident": e.execution.get("incident"), "watchdog_id": e.execution.get("watchdog_id")} for e in current.store.list() if e.execution] + (current.store.control("unexpected_incidents") or [])


@router.get("/api/healing/incidents/{incident_id}")
def incident(incident_id: str, request: Request):
    for row in platform(request).store.control("unexpected_incidents") or []:
        if row["id"] == incident_id:
            return row
    return action(lambda: platform(request).store.get(incident_id))


@router.get("/api/healing/actions")
def playbooks():
    return [{"name": "start_original_container_ids", "allowed": "Only previously running IDs recorded in the approved experiment lease", "forbidden": ["data deletion", "queue purge", "source modification", "arbitrary shell", "spontaneous auto-remediation"]}, {"name": "verify_readiness_dependencies_functionality_stability", "allowed": "Operator-configured, local, bounded HTTP GET probes"}]


@router.get("/api/healing/history")
def history(request: Request):
    return [event for event in platform(request).store.events() if event["kind"] in {"RECOVERY_ACTIONS", "VERIFICATION", "REPORT", "ERROR"}]


@router.get("/api/chaos/reports")
def reports(request: Request):
    return [e.report for e in platform(request).store.list() if e.report]


@router.get("/api/agents/status")
def agents(request: Request):
    current = platform(request)
    heartbeat = current.store.control("worker_heartbeat")
    return {"analysis": "available", "chaos": "enabled by disposable policy" if current.policy.enabled else "execution disabled", "self_healing": "restricted original-state recovery", "worker_alive": heartbeat is not None and current.store.clock() - heartbeat < 10, "kill_switch": current.safety.stopped(), "watchdog_verification_recorded": current.policy.watchdog_verified, "live_fault_verification": "Not performed by automated tests", "supported_faults": ["container_stop", "multi_container_stop", "service_restart", "rabbitmq_outage"], "unsupported_faults": ["database_outage", "network_latency", "packet_loss", "cpu_stress", "memory_pressure"], "timeline": current.store.events()[:100]}
