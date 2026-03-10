import asyncio
import subprocess
from pathlib import Path
from typing import Any

from app.agents.state import DriftAnalysisState
from app.services.git_service import commit_and_push_docs_branch
from app.services.github_api import (
    get_installation_access_token,
    create_docs_pull_request,
    request_pr_review,
    update_github_check_run,
)
from app.services.notification_service import create_notification
from app.db.base import DriftEvent


# Commits changes, pushes, and opens a docs PR
def _commit_and_pr(state: DriftAnalysisState) -> None:
    session = state["session"]
    drift_event_id = state["drift_event_id"]

    drift_event = session.query(DriftEvent).filter(DriftEvent.id == drift_event_id).first()
    if not drift_event:
        print(f"_commit_and_pr: DriftEvent {drift_event_id} not found")
        return

    repo = drift_event.repository
    session.refresh(repo)
    repo_full_name = repo.repo_name
    installation_id = repo.installation_id
    original_branch = drift_event.head_branch
    pr_number = drift_event.pr_number
    findings = state["findings"]
    rewrite_results = state.get("rewrite_results", [])

    # If no docs were actually rewritten, skip commit/push/PR entirely
    if not rewrite_results:
        print(f"_commit_and_pr: no rewrite results - skipping for event {drift_event_id}")
        return

    access_token = asyncio.run(get_installation_access_token(installation_id))

    # Commit and push changed .md files
    push_success = asyncio.run(
        commit_and_push_docs_branch(
            repo_path=state["repo_path"],
            pr_number=pr_number,
            access_token=access_token,
            repo_full_name=repo_full_name,
        )
    )

    if not push_success:
        print(f"_commit_and_pr: push failed for event {drift_event_id}")
        return

    # Get the current branch name (the docs branch we checked out earlier)
    branch_result = subprocess.run(
        ["git", "-C", state["repo_path"], "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    docs_branch = (
        branch_result.stdout.strip()
        if branch_result.returncode == 0
        else f"docs/delta-fix/{original_branch}"
    )

    # Create the docs PR targeting the original branch
    summary_lines = [f"- `{f.get('code_path', '?')}`: {f.get('explanation', '')}" for f in findings]
    drift_summary = "\n".join(summary_lines) if summary_lines else None
    updates_summary = state.get("doc_updates_summary") or None

    docs_pr_number = asyncio.run(
        create_docs_pull_request(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            head_branch=docs_branch,
            base_branch=original_branch,
            pr_number=pr_number,
            drift_summary=drift_summary,
            updates_summary=updates_summary,
        )
    )

    # Store the docs PR number in the drift event and update processing phase
    if docs_pr_number:
        drift_event.docs_pr_number = docs_pr_number
        drift_event.processing_phase = "fix_pr_raised"

        # Request review if a reviewer is configured for the repo
        if repo.reviewer:
            asyncio.run(
                request_pr_review(
                    installation_id=installation_id,
                    repo_full_name=repo_full_name,
                    pr_number=docs_pr_number,
                    reviewer=repo.reviewer,
                )
            )

        # Update the original check run to add Resolve link and add PR link to summary
        if drift_event.check_run_id:
            fix_pr_url = f"https://github.com/{repo_full_name}/pull/{docs_pr_number}"
            updated_summary = (
                drift_event.summary or ""
            ) + f"\n\n**Documentation Fixes:** [{repo_full_name}#{docs_pr_number}]({fix_pr_url})"
            try:
                asyncio.run(
                    update_github_check_run(
                        repo_full_name=repo_full_name,
                        check_run_id=drift_event.check_run_id,
                        installation_id=installation_id,
                        status="completed",
                        conclusion="action_required",
                        title="Documentation Drift Detected",
                        summary=updated_summary,
                        details_url=fix_pr_url,
                    )
                )
            except Exception as check_run_exc:
                print(f"Failed to update check run with fix PR link: {check_run_exc}")

    # Notify the user
    user_id = repo.installation.user_id if repo.installation else None
    if user_id:
        if docs_pr_number:
            create_notification(
                session,
                user_id,
                f"Documentation PR #{docs_pr_number} raised for {repo_full_name} to resolve drift found in PR #{pr_number}.",
            )

    session.commit()


# Node writes the rewritten content to the local .md files
def apply_changes(state: DriftAnalysisState) -> dict[str, Any]:
    rewrite_results: list[dict] = state["rewrite_results"]
    repo_path: str = state["repo_path"]

    for result in rewrite_results:
        doc_path = result["doc_path"]
        new_content = result["new_content"]

        full_path = Path(repo_path) / doc_path

        # Prevent path traversal outside the repo directory
        try:
            resolved = full_path.resolve()
            repo_resolved = Path(repo_path).resolve()
            if not str(resolved).startswith(str(repo_resolved)):
                print(f"Path traversal blocked for {doc_path}")
                continue
        except Exception:
            print(f"Could not resolve path {doc_path}")
            continue

        # Only write .md files
        if not doc_path.endswith(".md"):
            print(f"Skipping non-markdown file: {doc_path}")
            continue

        try:
            # Ensure the parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            print(f"Error writing {full_path}: {exc}")
            continue

    _commit_and_pr(state)
    return {}
