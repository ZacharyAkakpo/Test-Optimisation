"""Structures de données : un relevé en entrée, le rapport en sortie, et l'état du graphe."""

from datetime import timedelta
from typing import Any, Literal, TypedDict

from pydantic import AwareDatetime, BaseModel, Field

Status = Literal["online", "degraded", "offline"]
Severity = Literal["low", "medium", "high"]


# --- Entrée : un relevé du fichier de logs (les bornes rejettent les valeurs impossibles) ---
class LogRecord(BaseModel):
    timestamp: AwareDatetime
    cpu_usage: float = Field(ge=0, le=100)
    memory_usage: float = Field(ge=0, le=100)
    latency_ms: float = Field(ge=0)
    disk_usage: float = Field(ge=0, le=100)
    network_in_kbps: float = Field(ge=0)
    network_out_kbps: float = Field(ge=0)
    io_wait: float = Field(ge=0, le=100)
    thread_count: int = Field(ge=0)
    active_connections: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    uptime_seconds: int = Field(ge=0)
    temperature_celsius: float
    power_consumption_watts: float = Field(ge=0)
    service_status: dict[str, Status] = {}


# --- Sortie : exactement le schéma demandé ---
class Insights(BaseModel):
    average_latency_ms: float
    max_cpu_usage: float
    max_memory_usage: float
    error_rate: float
    uptime_seconds: float


class Anomaly(BaseModel):
    metric: str
    value: float
    threshold: float
    severity: Severity
    description: str


class Recommendation(BaseModel):
    id: str
    action: str
    target: str
    parameters: dict[str, Any]
    benefit_estimate: str


class ServiceStatusSummary(BaseModel):
    online: list[str] = []
    degraded: list[str] = []
    offline: list[str] = []


class Report(BaseModel):
    timestamp: str
    insights: Insights
    anomalies: list[Anomaly]
    recommendations: list[Recommendation]
    service_status_summary: ServiceStatusSummary


# --- État partagé entre les nœuds du graphe : chaque nœud ajoute ses clés ---
class State(TypedDict, total=False):
    input_path: str  # paramètres d'exécution
    use_llm: bool
    records: list[LogRecord]  # ingest
    step: timedelta
    insights: Insights  # analyze
    availability: dict[str, float]
    service_summary: ServiceStatusSummary
    anomalies: list[Anomaly]  # detect_anomalies
    recommendations: list[Recommendation]  # recommend / refine_with_llm
    source: str
    report: Report  # build_report
