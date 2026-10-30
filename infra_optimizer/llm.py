"""5. (optionnel) Claude réécrit et priorise les recommandations.

Le LLM ne calcule rien : il reçoit les anomalies et les recommandations déjà
produites, et renvoie pour chacune une formulation plus contextualisée, dans
l'ordre de priorité. Les paramètres techniques restent ceux du catalogue.
En cas de problème, on garde simplement les recommandations du catalogue.
"""

import json
import logging

import anthropic
from pydantic import BaseModel

from .config import LLM_EFFORT, LLM_MODEL
from .models import State

logger = logging.getLogger(__name__)

PROMPT = """Tu es ingénieur SRE senior et tu conseilles Jean, CTO d'une PME française.
Tu reçois en JSON les indicateurs, les anomalies détectées et les recommandations d'un moteur de règles.
Renvoie toutes les recommandations, triées par priorité (impact sur les utilisateurs d'abord), en gardant leur id.
Pour chacune, réécris `action` (une phrase concrète) et `benefit_estimate` (gain chiffré) en t'appuyant sur
les anomalies : récurrence, services touchés, chiffres mesurés. N'invente aucune mesure. Réponds en français."""


# Format de réponse imposé au modèle (vérifié automatiquement par Pydantic).
class RewrittenRecommendation(BaseModel):
    id: str
    action: str
    benefit_estimate: str


class LLMAnswer(BaseModel):
    recommendations: list[RewrittenRecommendation]


def refine_with_llm(state: State) -> State:
    context = {
        "insights": state["insights"].model_dump(),
        "anomalies": [a.model_dump() for a in state["anomalies"]],
        "recommendations": [r.model_dump() for r in state["recommendations"]],
    }
    try:
        response = anthropic.Anthropic().beta.messages.parse(
            model=LLM_MODEL,
            max_tokens=16000,
            output_config={"effort": LLM_EFFORT},
            # Si le modèle décline la requête, l'API la relance sur un modèle de repli.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=PROMPT,
            messages=[{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
            output_format=LLMAnswer,
        )
        answer = response.parsed_output
        if answer is None:
            raise ValueError("réponse vide")
    except (anthropic.APIError, ValueError) as error:  # réseau, clé invalide, quota, réponse non conforme...
        logger.warning("LLM indisponible (%s) : recommandations du catalogue conservées.", error)
        return {"source": "rules"}

    # On applique les nouveaux textes, dans l'ordre choisi par le LLM.
    by_id = {r.id: r for r in state["recommendations"]}
    rewritten = [
        by_id[item.id].model_copy(update={"action": item.action, "benefit_estimate": item.benefit_estimate})
        for item in answer.recommendations
        if item.id in by_id
    ]
    # Filet de sécurité : une recommandation oubliée par le LLM est remise à la fin.
    kept = {r.id for r in rewritten}
    rewritten += [r for r in state["recommendations"] if r.id not in kept]
    return {"recommendations": rewritten, "source": f"llm:{LLM_MODEL}"}
