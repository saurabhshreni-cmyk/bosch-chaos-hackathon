import hashlib
import json
from typing import Literal
from pydantic import Field, model_validator
from agent.schemas import StrictModel


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


Fault = Literal["container_stop", "multi_container_stop", "service_restart", "rabbitmq_outage", "database_outage", "network_latency", "packet_loss", "cpu_stress", "memory_pressure"]


class Probe(StrictModel):
    component: str
    url: str
    required_text: str = Field(min_length=1, max_length=200)
    purpose: Literal["readiness", "functionality", "dependency"]


class Policy(StrictModel):
    enabled: bool = False
    project: str = ""
    compose_file: str = ""
    allowed_services: list[str] = Field(default_factory=list, max_length=20)
    max_duration_seconds: int = Field(default=30, ge=1, le=60)
    max_targets: int = Field(default=1, ge=1, le=2)
    approval_ttl_seconds: int = Field(default=90, ge=10, le=120)
    stability_seconds: int = Field(default=5, ge=2, le=30)
    max_failed_probes: int = Field(default=30, ge=0, le=30)
    watchdog_image: str = "docker:cli"
    probes: list[Probe] = Field(default_factory=list, max_length=30)
    # Operator acknowledgement of a *separate* disposable verification, never inferred.
    watchdog_verified: bool = False

    @model_validator(mode="after")
    def isolated(self):
        if self.enabled and (not self.project.startswith("pfia-disposable-") or not self.compose_file or not self.allowed_services):
            raise ValueError("An enabled policy requires a pfia-disposable-* project, Compose path and allowlist")
        return self


class PlanRequest(StrictModel):
    source_finding_id: str = Field(min_length=1, max_length=200)
    targets: list[str] = Field(min_length=1, max_length=2)
    fault_type: Fault = "container_stop"
    duration_seconds: int = Field(default=15, ge=1, le=60)


class Proposal(PlanRequest):
    experiment_id: str
    title: str
    hypothesis: str
    expected_impact: list[str]
    metrics_to_monitor: list[str]
    rollback_action: Literal["start_original_container_ids"] = "start_original_container_ids"
    approval_required: Literal[True] = True
    source_configuration_hash: str
    source_prediction: dict
    policy_hash: str
    supported: bool
    unsupported_reason: str | None = None


class ApprovalRequest(StrictModel):
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation: Literal["I APPROVE THIS EXACT EXPERIMENT"]


class Experiment(StrictModel):
    id: str
    state: str
    proposal: Proposal
    proposal_hash: str
    created_at: float
    approval: dict | None = None
    execution: dict = Field(default_factory=dict)
    abort_requested: bool = False
    report: dict | None = None


TERMINAL = {"REJECTED", "CANCELLED", "EXPIRED", "INVALIDATED", "UNSUPPORTED", "COMPLETED", "INCONCLUSIVE"}
SUPPORTED = {"container_stop", "multi_container_stop", "service_restart", "rabbitmq_outage"}
UNSUPPORTED_REASONS = {
    "database_outage": "Disposable database volume and data isolation have not been verified.",
    "network_latency": "No validated network-namespace adapter and shaping-removal watchdog is integrated.",
    "packet_loss": "No validated packet-loss adapter and shaping-removal watchdog is integrated.",
    "cpu_stress": "A bounded stress tool, resource isolation and reliable rollback have not been verified.",
    "memory_pressure": "A bounded stress tool, memory isolation and reliable rollback have not been verified.",
}
