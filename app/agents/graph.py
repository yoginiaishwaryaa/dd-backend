from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.agents.state import DriftAnalysisState
from app.agents.nodes import (
    scout_changes,
    retrieve_docs,
    deep_analyze,
    aggregate_results,
    plan_updates,
    rewrite_docs,
    apply_changes,
)


# Route to doc gen if drift is found else end the graph execution
def should_generate_docs(state: DriftAnalysisState) -> str:
    findings = state.get("findings", [])
    if findings:
        return "plan_updates"
    return "__end__"


# Build and compile the Delta LangGraph workflow
def build_drift_analysis_graph() -> CompiledStateGraph:
    graph = StateGraph(DriftAnalysisState)  # type: ignore[bad-specialization]

    # Drift analysis nodes
    graph.add_node("scout_changes", scout_changes)  # type: ignore[no-matching-overload]
    graph.add_node("retrieve_docs", retrieve_docs)  # type: ignore[no-matching-overload]
    graph.add_node("deep_analyze", deep_analyze)  # type: ignore[no-matching-overload]
    graph.add_node("aggregate_results", aggregate_results)  # type: ignore[no-matching-overload]

    # Document generation nodes
    graph.add_node("plan_updates", plan_updates)  # type: ignore[no-matching-overload]
    graph.add_node("rewrite_docs", rewrite_docs)  # type: ignore[no-matching-overload]
    graph.add_node("apply_changes", apply_changes)  # type: ignore[no-matching-overload]

    # Drift analysis edges
    graph.add_edge(START, "scout_changes")
    graph.add_edge("scout_changes", "retrieve_docs")
    graph.add_edge("retrieve_docs", "deep_analyze")
    graph.add_edge("deep_analyze", "aggregate_results")

    # Conditional: generate docs if drift found, else end
    graph.add_conditional_edges("aggregate_results", should_generate_docs)

    # Document generation edges
    graph.add_edge("plan_updates", "rewrite_docs")
    graph.add_edge("rewrite_docs", "apply_changes")
    graph.add_edge("apply_changes", END)

    return graph.compile()


drift_analysis_graph = build_drift_analysis_graph()
