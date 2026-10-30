"""Tests du pipeline : petits jeux de données fabriqués + jeu de données fourni."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from infra_optimizer import llm
from infra_optimizer.__main__ import main
from infra_optimizer.graph import llm_or_report, run_pipeline

DATASET = Path(__file__).parent.parent / "data" / "rapport.json"


def make_records(count=40, spikes=(), outages=()):
    """Relevés normaux toutes les 30 min, avec des pics de charge et des coupures de la base aux indices donnés."""
    records = []
    for i in range(count):
        record = {
            "timestamp": (datetime(2023, 10, 1, tzinfo=UTC) + i * timedelta(minutes=30)).isoformat(),
            "cpu_usage": 55, "memory_usage": 65, "latency_ms": 130, "disk_usage": 60,
            "network_in_kbps": 1200, "network_out_kbps": 1100, "io_wait": 3, "thread_count": 150,
            "active_connections": 50, "error_rate": 0.02, "uptime_seconds": 360000 + 1800 * i,
            "temperature_celsius": 60, "power_consumption_watts": 250,
            "service_status": {"database": "online", "api_gateway": "online", "cache": "online"},
        }
        if i in spikes:
            record |= {"cpu_usage": 95, "latency_ms": 350, "error_rate": 0.12}
            record["service_status"]["api_gateway"] = "degraded"
        if i in outages:
            record["service_status"]["database"] = "offline"
        records.append(record)
    return records


@pytest.fixture
def run(tmp_path):
    """Exécute le pipeline (sans LLM) sur une liste de relevés et renvoie l'état final."""

    def _run(records):
        path = tmp_path / "logs.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        return run_pipeline(path, use_llm=False)

    return _run


def anomaly(state, metric):
    return next(a for a in state["anomalies"] if a.metric == metric)


# --- Détection et recommandations sur des données fabriquées ---


def test_healthy_data_gives_empty_report(run):
    state = run(make_records())
    assert state["anomalies"] == []
    assert state["recommendations"] == []


def test_invalid_records_are_skipped(run):
    records = make_records()
    records[1]["cpu_usage"] = 150  # pourcentage impossible
    assert len(run(records)["records"]) == 39


def test_recurring_cpu_spikes(run):
    state = run(make_records(spikes=range(0, 40, 10)))  # un pic toutes les 5 h
    cpu = anomaly(state, "cpu_usage")
    assert (cpu.value, cpu.threshold, cpu.severity) == (95, 90, "high")
    assert "toutes les 5 h" in cpu.description
    assert [r.id for r in state["recommendations"]] == ["REC-AUTOSCALING", "REC-API-GATEWAY", "REC-OBSERVABILITY"]
    assert "95 %" in state["recommendations"][0].benefit_estimate  # valeur mesurée insérée dans le texte


def test_database_outages(run):
    state = run(make_records(outages=range(3, 40, 7)))  # une coupure toutes les 3h30
    database = anomaly(state, "database_availability_pct")
    assert (database.value, database.severity) == (85.0, "high")
    assert "toutes les 3.5 h" in database.description
    assert state["service_summary"].offline == ["database"]
    assert state["recommendations"][0].id == "REC-DB-RELIABILITY"


# --- Jeu de données fourni et ligne de commande ---


def test_full_dataset():
    state = run_pipeline(DATASET, use_llm=False)
    insights = state["insights"]
    assert (insights.max_cpu_usage, insights.max_memory_usage, insights.uptime_seconds) == (99, 92, 1258200)
    assert insights.average_latency_ms == pytest.approx(156.02)
    assert state["service_summary"].degraded == ["api_gateway", "cache"]
    assert len(state["anomalies"]) == 15
    assert state["recommendations"][0].id == "REC-DB-RELIABILITY"


def test_cli_writes_report_with_expected_schema(tmp_path):
    output = tmp_path / "output.json"
    assert main(["--input", str(DATASET), "--output", str(output), "--no-llm"]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert set(report) == {"timestamp", "insights", "anomalies", "recommendations", "service_status_summary"}
    assert set(report["anomalies"][0]) == {"metric", "value", "threshold", "severity", "description"}
    assert set(report["recommendations"][0]) == {"id", "action", "target", "parameters", "benefit_estimate"}


def test_cli_fails_cleanly_on_missing_file(tmp_path):
    assert main(["--input", str(tmp_path / "absent.json"), "--no-llm"]) == 1


# --- LLM (simulé : aucun appel réseau) ---


def fake_claude(monkeypatch, answer):
    """Remplace le client Anthropic par un faux qui renvoie `answer`."""
    messages = SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(parsed_output=answer))
    monkeypatch.setattr(llm.anthropic, "Anthropic", lambda: SimpleNamespace(beta=SimpleNamespace(messages=messages)))


def test_llm_is_only_used_with_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_or_report({"use_llm": True}) == "build_report"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert llm_or_report({"use_llm": True}) == "refine_with_llm"
    assert llm_or_report({"use_llm": False}) == "build_report"


def test_llm_rewrites_and_reorders(monkeypatch, run):
    state = run(make_records(spikes=range(0, 40, 10)))
    rewritten = llm.RewrittenRecommendation(id="REC-API-GATEWAY", action="Nouvelle action", benefit_estimate="Nouveau gain")
    fake_claude(monkeypatch, llm.LLMAnswer(recommendations=[rewritten]))

    result = llm.refine_with_llm(state)

    first = result["recommendations"][0]
    assert (first.id, first.action, first.benefit_estimate) == ("REC-API-GATEWAY", "Nouvelle action", "Nouveau gain")
    assert first.parameters == state["recommendations"][1].parameters  # paramètres inchangés
    assert len(result["recommendations"]) == 3  # les recommandations oubliées sont gardées


def test_llm_failure_keeps_rule_recommendations(monkeypatch, run):
    state = run(make_records(spikes=range(0, 40, 10)))
    fake_claude(monkeypatch, None)  # réponse vide (ex. requête déclinée)
    assert llm.refine_with_llm(state) == {"source": "rules"}
