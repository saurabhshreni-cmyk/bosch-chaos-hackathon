"""Public contracts. AI narrative cannot contain scores or execution instructions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    path: str
    line: int = Field(ge=1)
    description: str


class Service(StrictModel):
    name: str
    role: str
    runtime: str
    framework: str = "not established"
    dockerfile: str | None = None
    build_images: list[str] = []
    ports: list[str] = []
    networks: list[str] = []
    replicas: int = Field(default=1, ge=0)
    limits: dict = {}
    restart: str = "not configured"
    healthcheck: bool = False
    health_path: str | None = None
    environment_names: list[str] = []
    code_paths: list[str] = []
    controls: list[str] = []
    routes: list[str] = []


class Dependency(StrictModel):
    source: str
    target: str
    kind: Literal["startup", "http", "database", "broker", "logging", "mail", "event"]
    confidence: Literal["high", "medium"]
    evidence: Evidence
    detail: str


class Finding(StrictModel):
    id: str
    component: str
    title: str
    severity: Literal["low", "medium", "high"]
    status: Literal["verified configuration", "evidence-supported hypothesis", "unverified possibility"]
    evidence: list[Evidence]
    scenario: str
    mitigation: str


class Metric(StrictModel):
    component: str
    container_id: str
    timestamp: float
    state: str
    health: str
    cpu_percent: float | None = None
    memory_bytes: int = 0
    configured_memory_limit: int | None = None
    stats_memory_limit: int | None = None
    restart_count: int = 0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0
    host: str = "local Docker engine"


class Risk(StrictModel):
    component: str
    score: float = Field(ge=0, le=100)
    evidence_coverage: float = Field(ge=0, le=1)
    factors: dict[str, float]
    missing_evidence: list[str]
    affected_dependents: list[str]
    primary_concerns: list[str] = []
    dependencies: list[str] = []
    supporting_evidence: list[Evidence] = []
    failure_scenarios: list[str] = []
    mitigations: list[str] = []
    proposed_verification: str = "Verify in an authorized disposable environment with bounded duration, independent recovery and business-level health checks. PFIA does not execute this recommendation."


class ScenarioRequest(StrictModel):
    kind: Literal["traffic", "database", "broker", "network", "resource", "cascade", "container", "host"]
    target: str | None = None
    traffic_multiplier: Literal[2, 5, 10] = 2
    latency_ms: int = Field(default=100, ge=0, le=10000)
    packet_loss_percent: float = Field(default=0, ge=0, le=100)


class AnalyzeRequest(StrictModel):
    runtime: bool = False
    use_groq: bool = False


class Insight(StrictModel):
    component: str
    evidence_ids: list[str]
    hypothesis: str = Field(min_length=1, max_length=2000)
    mitigation: str = Field(min_length=1, max_length=1000)
    verification: str = Field(min_length=1, max_length=1000)


class Narrative(StrictModel):
    hypotheses: list[Insight] = Field(max_length=20)
    missing_evidence: list[str] = Field(max_length=30)
