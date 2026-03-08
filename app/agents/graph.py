import asyncio
import subprocess
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.agents.state import DriftAnalysisState
from app.agents.nodes.scout_changes import scout_changes
from app.agents.nodes.retrieve_docs import retrieve_docs
from app.agents.nodes.deep_analyze import deep_analyze
from app.agents.nodes.aggregate_results import aggregate_results
from app.agents.nodes.doc_gen_nodes import plan_updates, rewrite_docs, apply_changes

from app.services.git_service import checkout_docs_branch, commit_and_push_docs
from app.services.github_api import (
    get_installation_access_token,
    create_docs_pull_request,
)
from app.services.notification_service import create_notification
from app.db.base import DriftEvent


# Wrapper node: creates a docs branch off the original PR branch
def checkout_docs(state: DriftAnalysisState) -> dict[str, Any]:
    session = state["session"]
    drift_event_id = state["drift_event_id"]

    drift_event = session.query(DriftEvent).filter(DriftEvent.id == drift_event_id).first()
    if not drift_event:
        print(f"checkout_docs: DriftEvent {drift_event_id} not found")
        return {}

    repo = drift_event.repository
    repo_full_name = repo.repo_name
    installation_id = repo.installation_id
    original_branch = drift_event.head_branch

    access_token = asyncio.run(get_installation_access_token(installation_id))
    branch_name = asyncio.run(
        checkout_docs_branch(
            repo_path=state["repo_path"],
            original_branch=original_branch,
            access_token=access_token,
            repo_full_name=repo_full_name,
        )
    )

    if not branch_name:
        raise RuntimeError(f"Failed to create docs branch for event {drift_event_id}")

    # Update event phase
    drift_event.processing_phase = "generating"
    session.commit()

    print(f"Checked out docs branch: {branch_name}")
    return {}


# Wrapper node: commits changes, pushes, and opens a docs PR
def commit_and_pr(state: DriftAnalysisState) -> dict[str, Any]:
    session = state["session"]
    drift_event_id = state["drift_event_id"]

    drift_event = session.query(DriftEvent).filter(DriftEvent.id == drift_event_id).first()
    if not drift_event:
        print(f"commit_and_pr: DriftEvent {drift_event_id} not found")
        return {}

    repo = drift_event.repository
    repo_full_name = repo.repo_name
    installation_id = repo.installation_id
    original_branch = drift_event.head_branch
    pr_number = drift_event.pr_number
    findings = state["findings"]
    rewrite_results = state.get("rewrite_results", [])

    # If no docs were actually rewritten, skip commit/push/PR entirely
    if not rewrite_results:
        print(f"commit_and_pr: no rewrite results — skipping for event {drift_event_id}")
        return {}

    access_token = asyncio.run(get_installation_access_token(installation_id))

    # Commit and push changed .md files
    push_success = asyncio.run(
        commit_and_push_docs(
            repo_path=state["repo_path"],
            pr_number=pr_number,
            access_token=access_token,
            repo_full_name=repo_full_name,
        )
    )

    if not push_success:
        print(f"commit_and_pr: push failed for event {drift_event_id}")
        return {}

    # Get the current branch name (the docs branch we checked out earlier)
    branch_result = subprocess.run(
        ["git", "-C", state["repo_path"], "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    docs_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else f"docs/drift-fix/{original_branch}"

    # Create the docs PR targeting the original branch
    summary_lines = [f"- `{f.get('code_path', '?')}`: {f.get('explanation', '')}" for f in findings]
    docs_summary = "\n".join(summary_lines) if summary_lines else "Auto-generated documentation fixes."

    docs_pr_number = asyncio.run(
        create_docs_pull_request(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            head_branch=docs_branch,
            base_branch=original_branch,
            pr_number=pr_number,
            changes_summary=docs_summary,
        )
    )

    # Notify the user
    user_id = repo.installation.user_id if repo.installation else None
    if user_id:
        if docs_pr_number:
            create_notification(
                session,
                user_id,
                f"Documentation PR #{docs_pr_number} created for {repo_full_name} to resolve drift found in PR #{pr_number}.",
            )
        else:
            create_notification(
                session,
                user_id,
                f"Document generation for PR #{pr_number} in {repo_full_name} completed but PR creation failed.",
            )

    session.commit()
    print(f"Docs PR #{docs_pr_number} created for event {drift_event_id}")
    return {}


# Conditional edge: route to doc gen if drift was found, otherwise end
def should_generate_docs(state: DriftAnalysisState) -> str:
    findings = state.get("findings", [])
    if findings:
        return "checkout_docs"
    return "__end__"


# Build and compile the drift analysis + document generation LangGraph workflow
def build_drift_analysis_graph() -> CompiledStateGraph:
    graph = StateGraph(DriftAnalysisState)  # type: ignore[bad-specialization]

    # Drift analysis nodes
    graph.add_node("scout_changes", scout_changes)  # type: ignore[no-matching-overload]
    graph.add_node("retrieve_docs", retrieve_docs)  # type: ignore[no-matching-overload]
    graph.add_node("deep_analyze", deep_analyze)  # type: ignore[no-matching-overload]
    graph.add_node("aggregate_results", aggregate_results)  # type: ignore[no-matching-overload]

    # Document generation nodes
    graph.add_node("checkout_docs", checkout_docs)  # type: ignore[no-matching-overload]
    graph.add_node("plan_updates", plan_updates)  # type: ignore[no-matching-overload]
    graph.add_node("rewrite_docs", rewrite_docs)  # type: ignore[no-matching-overload]
    graph.add_node("apply_changes", apply_changes)  # type: ignore[no-matching-overload]
    graph.add_node("commit_and_pr", commit_and_pr)  # type: ignore[no-matching-overload]

    # Drift analysis edges
    graph.add_edge(START, "scout_changes")
    graph.add_edge("scout_changes", "retrieve_docs")
    graph.add_edge("retrieve_docs", "deep_analyze")
    graph.add_edge("deep_analyze", "aggregate_results")

    # Conditional: generate docs if drift found, else end
    graph.add_conditional_edges("aggregate_results", should_generate_docs)

    # Document generation edges
    graph.add_edge("checkout_docs", "plan_updates")
    graph.add_edge("plan_updates", "rewrite_docs")
    graph.add_edge("rewrite_docs", "apply_changes")
    graph.add_edge("apply_changes", "commit_and_pr")
    graph.add_edge("commit_and_pr", END)

    return graph.compile()


drift_analysis_graph = build_drift_analysis_graph()
