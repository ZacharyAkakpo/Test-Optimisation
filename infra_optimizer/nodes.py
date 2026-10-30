"""Les étapes du pipeline. Chaque nœud reçoit l'état et renvoie les clés qu'il y ajoute."""

import json
import logging
import statistics
from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from pydantic import ValidationError

from .config import RECURRENCE_MIN_SHARE, SERVICE_SLO_PCT, THRESHOLDS
from .models import (
    Anomaly,
    Insights,
    LogRecord,
    Recommendation,
    Report,
    ServiceStatusSummary,
    State,
)
from .playbook import PLAYBOOK

logger = logging.getLogger(__name__)

# Sévérités, de la plus grave à la moins grave, avec leur libellé dans les descriptions.
SEVERITIES = {"high": "critique", "medium": "majeur", "low": "alerte"}


def ingest(state: State) -> State:
    """1. Lit le fichier JSON et garde les relevés valides, triés par date."""
    data = json.loads(Path(state["input_path"]).read_text(encoding="utf-8"))
    if isinstance(data, dict):  # l'énoncé montre un relevé seul, le fichier fourni une liste
        data = [data]

    records = []
    for index, item in enumerate(data):
        try:
            records.append(LogRecord.model_validate(item))
        except ValidationError:
            logger.warning("Relevé n°%d ignoré : format invalide.", index)
    if not records:
        raise ValueError("Aucun relevé valide dans le fichier.")

    records.sort(key=lambda r: r.timestamp)
    gaps = [b.timestamp - a.timestamp for a, b in pairwise(records)]
    step = statistics.median(gaps) if gaps else timedelta(0)  # intervalle habituel entre deux relevés
    return {"records": records, "step": step}


def analyze(state: State) -> State:
    """2. Calcule les indicateurs globaux et la disponibilité de chaque service."""
    records = state["records"]
    insights = Insights(
        average_latency_ms=round(statistics.mean(r.latency_ms for r in records), 2),
        max_cpu_usage=max(r.cpu_usage for r in records),
        max_memory_usage=max(r.memory_usage for r in records),
        error_rate=round(statistics.mean(r.error_rate for r in records), 4),
        uptime_seconds=records[-1].uptime_seconds,  # uptime au dernier relevé
    )

    availability = {}
    summary = ServiceStatusSummary()
    for service in sorted({name for r in records for name in r.service_status}):
        statuses = [r.service_status[service] for r in records if service in r.service_status]
        availability[service] = round(100 * statuses.count("online") / len(statuses), 1)
        # On classe le service selon son pire statut sur la période, pour ne pas masquer les incidents.
        worst = "offline" if "offline" in statuses else "degraded" if "degraded" in statuses else "online"
        getattr(summary, worst).append(service)

    return {"insights": insights, "availability": availability, "service_summary": summary}


def detect_anomalies(state: State) -> State:
    """3. Compare chaque métrique à ses seuils et chaque service à son objectif de disponibilité."""
    records, step = state["records"], state["step"]
    anomalies = []

    for metric, t in THRESHOLDS.items():
        breaches = [r for r in records if getattr(r, metric) >= t["low"]]
        if not breaches:
            continue
        peak = max(getattr(r, metric) for r in breaches)
        severity = next(s for s in SEVERITIES if peak >= t[s])  # niveau le plus grave atteint
        share = 100 * len(breaches) / len(records)
        description = (
            f"{t['label']} : pic à {fmt(peak, t['unit'])} (seuil {SEVERITIES[severity]} : {fmt(t[severity], t['unit'])}), "
            f"{len(breaches)} relevés au-dessus de {fmt(t['low'], t['unit'])} ({share:.1f} % du temps)."
            + recurrence([r.timestamp for r in breaches], step)
        )
        anomalies.append(Anomaly(metric=metric, value=peak, threshold=t[severity], severity=severity, description=description))

    for service, pct in state["availability"].items():
        if pct >= SERVICE_SLO_PCT:
            continue
        incidents = [r for r in records if r.service_status.get(service, "online") != "online"]
        offline = sum(r.service_status[service] == "offline" for r in incidents)
        error_rate = statistics.mean(r.error_rate for r in incidents)
        description = (
            f"Service {service} : disponible {pct:g} % du temps (objectif {SERVICE_SLO_PCT:g} %), "
            f"{offline} relevés hors ligne et {len(incidents) - offline} dégradés. "
            f"Taux d'erreur moyen pendant ces incidents : {error_rate:.3f} (moyenne globale : {state['insights'].error_rate:.3f})."
            + recurrence([r.timestamp for r in incidents], step)
        )
        anomalies.append(
            Anomaly(
                metric=f"{service}_availability_pct",
                value=pct,
                threshold=SERVICE_SLO_PCT,
                severity="high" if offline else "medium",
                description=description,
            )
        )

    anomalies.sort(key=lambda a: list(SEVERITIES).index(a.severity))  # les plus graves d'abord
    return {"anomalies": anomalies}


def recommend(state: State) -> State:
    """4. Retient dans le catalogue (playbook.py) les recommandations déclenchées par les anomalies."""
    in_anomaly = {a.metric for a in state["anomalies"]}
    values = measured_values(state)

    recommendations = []
    for rec in PLAYBOOK:
        triggered = in_anomaly if rec["when"] == "*" else in_anomaly & set(rec["when"])
        if triggered:
            recommendations.append(
                Recommendation(
                    id=rec["id"],
                    action=rec["action"].format(**values),
                    target=rec["target"],
                    parameters=rec["parameters"],
                    benefit_estimate=rec["benefit_estimate"].format(**values),
                )
            )
    return {"recommendations": recommendations, "source": "rules"}


def build_report(state: State) -> State:
    """6. Assemble le rapport final au format demandé."""
    report = Report(
        timestamp=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        insights=state["insights"],
        anomalies=state["anomalies"],
        recommendations=state["recommendations"],
        service_status_summary=state["service_summary"],
    )
    return {"report": report}


# --- Petites fonctions utilitaires ---


def fmt(value: float, unit: str) -> str:
    """99.0, '%' -> '99 %' ; 0.13, '' -> '0.13'"""
    return f"{value:g} {unit}".strip()


def recurrence(timestamps: list[datetime], step: timedelta) -> str:
    """Renvoie « Récurrent : toutes les X h. » si la plupart des incidents sont espacés de la même durée."""
    gaps = [b - a for a, b in pairwise(timestamps) if b - a > step]  # on ignore les relevés consécutifs
    if len(gaps) < 2:
        return ""
    gap, count = Counter(gaps).most_common(1)[0]
    if count / len(gaps) < RECURRENCE_MIN_SHARE:
        return ""
    return f" Récurrent : toutes les {gap.total_seconds() / 3600:g} h."


def measured_values(state: State) -> dict[str, str]:
    """Valeurs que les textes du catalogue peuvent citer : {cpu_usage_max}, {cache_availability_pct}..."""
    values = {"sampling_minutes": f"{state['step'].total_seconds() / 60:g}"}
    for metric in THRESHOLDS:
        column = [getattr(r, metric) for r in state["records"]]
        values[f"{metric}_max"] = f"{max(column):g}"
        values[f"{metric}_median"] = f"{statistics.median(column):g}"
    for service, pct in state["availability"].items():
        values[f"{service}_availability_pct"] = f"{pct:g}"
    return values
