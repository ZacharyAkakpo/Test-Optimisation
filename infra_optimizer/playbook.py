"""Catalogue des recommandations.

Chaque recommandation est déclenchée dès qu'une des métriques de `when` est en
anomalie ("*" = dès qu'il y a au moins une anomalie). L'ordre de la liste est
l'ordre de priorité dans le rapport.

Les textes peuvent citer des valeurs mesurées entre accolades :
  {cpu_usage_max}, {latency_ms_median}...  -> pic / médiane d'une métrique
  {database_availability_pct}              -> disponibilité d'un service (%)
  {sampling_minutes}                       -> intervalle entre deux relevés

Ajouter une recommandation = ajouter un dictionnaire à cette liste.
"""

PLAYBOOK = [
    {
        "id": "REC-DB-RELIABILITY",
        "when": ["database_availability_pct"],
        "target": "database",
        "action": "Diagnostiquer les coupures récurrentes de la base de données (tâche planifiée, sonde de santé trop sensible), puis ajouter un réplica avec bascule automatique",
        "parameters": {
            "health_check": {"interval_seconds": 10, "failure_threshold": 3},
            "standby_replicas": 1,
            "failover": "automatic",
            "client_retry": {"max_attempts": 3, "backoff": "exponential"},
        },
        "benefit_estimate": "Disponibilité de la base de {database_availability_pct} % à plus de 99.9 %.",
    },
    {
        "id": "REC-AUTOSCALING",
        "when": ["cpu_usage", "memory_usage", "active_connections"],
        "target": "application_servers",
        "action": "Mettre en place un autoscaling horizontal des serveurs applicatifs, déclenché à 65 % de CPU, et ajouter de la capacité avant les pics récurrents",
        "parameters": {
            "scaling_metric": "cpu_usage",
            "target_cpu_pct": 65,
            "min_replicas": 2,
            "max_replicas": 4,
            "scale_out_cooldown_seconds": 60,
            "scale_in_cooldown_seconds": 600,
        },
        "benefit_estimate": "CPU de pointe ramené de {cpu_usage_max} % à environ 65 % ; latence de pointe ramenée de {latency_ms_max} ms vers son niveau normal ({latency_ms_median} ms).",
    },
    {
        "id": "REC-API-GATEWAY",
        "when": ["api_gateway_availability_pct", "error_rate"],
        "target": "api_gateway",
        "action": "Protéger l'API gateway : répartition de charge least-connections, limitation de débit par client et circuit breaker vers les services amont",
        "parameters": {
            "load_balancing": "least_connections",
            "rate_limit": {"strategy": "token_bucket", "burst_pct": 20},
            "circuit_breaker": {"error_rate_threshold": 0.05, "open_seconds": 30},
        },
        "benefit_estimate": "Disponibilité de l'API gateway de {api_gateway_availability_pct} % à plus de 99 % ; taux d'erreur de pointe ({error_rate_max}) contenu sous 0.05.",
    },
    {
        "id": "REC-CACHE-THREADS",
        "when": ["cache_availability_pct", "thread_count"],
        "target": "cache",
        "action": "Stabiliser le cache : identifier le traitement récurrent qui le dégrade, plafonner le pool de threads et revoir la politique d'éviction",
        "parameters": {
            "thread_pool_max_size": 170,
            "eviction_policy": "allkeys-lru",
            "memory_headroom_pct": 20,
        },
        "benefit_estimate": "Disponibilité du cache de {cache_availability_pct} % à plus de 99 % ; fin des pics de threads (jusqu'à {thread_count_max} contre {thread_count_median} habituellement).",
    },
    {
        "id": "REC-STORAGE-IO",
        "when": ["disk_usage", "io_wait"],
        "target": "storage",
        "action": "Sécuriser le stockage : rotation des logs, fichiers temporaires sur un volume dédié, extension du volume de 30 % et passage à un stockage SSD plus rapide",
        "parameters": {
            "log_retention_days": 7,
            "volume_extension_pct": 30,
            "disk_alert_pct": 80,
            "storage_tier": "SSD NVMe",
        },
        "benefit_estimate": "Pic disque de {disk_usage_max} % ramené sous 75 % ; attente I/O de pointe de {io_wait_max} % ramenée vers {io_wait_median} %.",
    },
    {
        "id": "REC-THERMAL-POWER",
        "when": ["temperature_celsius", "power_consumption_watts"],
        "target": "servers_hardware",
        "action": "Contrôler le refroidissement des serveurs (flux d'air, ventilateurs, climatisation) et alerter au-delà de 80 °C",
        "parameters": {
            "temperature_alert_celsius": 80,
            "temperature_critical_celsius": 85,
            "rack_inlet_max_celsius": 27,
        },
        "benefit_estimate": "Température de pointe de {temperature_celsius_max} °C ramenée sous 80 °C ; consommation de pointe ({power_consumption_watts_max} W) ramenée vers {power_consumption_watts_median} W une fois la charge répartie.",
    },
    {
        "id": "REC-OBSERVABILITY",
        "when": "*",
        "target": "monitoring",
        "action": "Renforcer la supervision : un relevé par minute au lieu d'un toutes les {sampling_minutes} min, et des alertes sur les seuils de ce rapport",
        "parameters": {
            "collection_interval_seconds": 60,
            "alert_levels": ["warning", "critical"],
        },
        "benefit_estimate": "Incidents détectés en 1 à 2 minutes au lieu de {sampling_minutes}, et durée réelle des coupures enfin mesurable.",
    },
]
