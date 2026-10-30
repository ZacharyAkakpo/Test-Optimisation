"""Tous les réglages du projet. Modifier un seuil = modifier une ligne ici."""

import os

# Seuils par métrique : au-delà de `low` c'est une anomalie, et la sévérité
# retenue est le niveau le plus élevé atteint par le pic.
THRESHOLDS = {
    "cpu_usage":               {"label": "CPU",                "unit": "%",    "low": 70,   "medium": 80,   "high": 90},
    "memory_usage":            {"label": "Mémoire",            "unit": "%",    "low": 75,   "medium": 85,   "high": 90},
    "latency_ms":              {"label": "Latence",            "unit": "ms",   "low": 200,  "medium": 250,  "high": 300},
    "disk_usage":              {"label": "Disque",             "unit": "%",    "low": 80,   "medium": 85,   "high": 90},
    "io_wait":                 {"label": "Attente I/O",        "unit": "%",    "low": 7,    "medium": 10,   "high": 15},
    "error_rate":              {"label": "Taux d'erreur",      "unit": "",     "low": 0.05, "medium": 0.08, "high": 0.10},
    "temperature_celsius":     {"label": "Température",        "unit": "°C",   "low": 70,   "medium": 80,   "high": 85},
    "active_connections":      {"label": "Connexions actives", "unit": "",     "low": 75,   "medium": 100,  "high": 120},
    "thread_count":            {"label": "Threads",            "unit": "",     "low": 170,  "medium": 180,  "high": 190},
    "network_in_kbps":         {"label": "Réseau entrant",     "unit": "kbps", "low": 1800, "medium": 2200, "high": 2600},
    "network_out_kbps":        {"label": "Réseau sortant",     "unit": "kbps", "low": 1600, "medium": 1900, "high": 2200},
    "power_consumption_watts": {"label": "Consommation",       "unit": "W",    "low": 300,  "medium": 340,  "high": 380},
}

# Un service est en anomalie s'il est "online" moins de 99 % du temps.
SERVICE_SLO_PCT = 99.0

# Une anomalie est dite récurrente si au moins 50 % des intervalles entre deux
# incidents ont la même durée.
RECURRENCE_MIN_SHARE = 0.5

# LLM (optionnel) : utilisé seulement si ANTHROPIC_API_KEY est définie.
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "medium")
