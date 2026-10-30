"""Le pipeline sous forme de graphe LangGraph :

    ingest -> analyze -> detect_anomalies -> recommend -> (refine_with_llm) -> build_report
"""

import os

from langgraph.graph import END, START, StateGraph

from .llm import refine_with_llm
from .models import State
from .nodes import analyze, build_report, detect_anomalies, ingest, recommend


def llm_or_report(state: State) -> str:
    """Après les règles, on passe par le LLM seulement s'il est activé et qu'une clé API existe."""
    if state.get("use_llm") and os.getenv("ANTHROPIC_API_KEY"):
        return "refine_with_llm"
    return "build_report"


def build_graph():
    graph = StateGraph(State)
    graph.add_sequence([ingest, analyze, detect_anomalies, recommend])
    graph.add_node(refine_with_llm)
    graph.add_node(build_report)

    graph.add_edge(START, "ingest")
    graph.add_conditional_edges("recommend", llm_or_report, ["refine_with_llm", "build_report"])
    graph.add_edge("refine_with_llm", "build_report")
    graph.add_edge("build_report", END)
    return graph.compile()


def run_pipeline(input_path, use_llm: bool = True) -> State:
    return build_graph().invoke({"input_path": str(input_path), "use_llm": use_llm})
