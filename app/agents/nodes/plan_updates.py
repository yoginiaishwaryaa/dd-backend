import asyncio
from pathlib import Path
from typing import Any, cast
from app.db.base import DriftEvent
from app.schemas.llm import UpdatePlan
from app.agents.llm import get_llm
from app.agents.state import DriftAnalysisState
from app.services.git_service import create_docs_branch
from app.agents.prompts import DOC_GEN_PLAN_SYSTEM_PROMPT, build_doc_gen_plan_user_prompt
from app.services.github_api import get_installation_access_token


# Creates a docs branch off the original PR branch
def _checkout_docs(state: DriftAnalysisState) -> None:
    session = state["session"]
    drift_event_id = state["drift_event_id"]

    drift_event = session.query(DriftEvent).filter(DriftEvent.id == drift_event_id).first()
    if not drift_event:
        print(f"_checkout_docs: DriftEvent {drift_event_id} not found")
        return

    repo = drift_event.repository
    repo_full_name = repo.repo_name
    installation_id = repo.installation_id
    original_branch = drift_event.head_branch
    pr_number = drift_event.pr_number

    access_token = asyncio.run(get_installation_access_token(installation_id))
    branch_name = asyncio.run(
        create_docs_branch(
            repo_path=state["repo_path"],
            original_branch=original_branch,
            access_token=access_token,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
        )
    )

    if not branch_name:
        raise RuntimeError(f"Failed to create docs branch for event {drift_event_id}")

    drift_event.processing_phase = "generating"
    session.commit()


# Node analyses drift findings and maps them to specific doc files/sections
def plan_updates(state: DriftAnalysisState) -> dict[str, Any]:
    _checkout_docs(state)

    drift_findings: list[dict] = state["findings"]
    repo_path: str = state["repo_path"]

    if not drift_findings:
        return {"target_files": []}

    # Discover actual .md files in the repo so the LLM doesn't hallucinate paths
    repo_root = Path(repo_path)
    existing_md_files = [
        str(p.relative_to(repo_root)).replace("\\", "/")
        for p in repo_root.rglob("*.md")
        if ".git" not in p.parts
    ]

    if not existing_md_files:
        print("plan_updates: no .md files found in repo")
        return {"target_files": []}

    # Initialise Gemini with structured output bound to UpdatePlan
    structured_llm = get_llm().with_structured_output(UpdatePlan)

    # Build user prompt with all findings AND the list of real doc files
    user_prompt = build_doc_gen_plan_user_prompt(existing_md_files, drift_findings)

    try:
        raw_result = structured_llm.invoke(
            [
                {"role": "system", "content": DOC_GEN_PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        plan = cast(UpdatePlan, raw_result)
    except Exception as exc:
        print(f"LLM error in plan_updates: {exc}")
        return {"target_files": []}

    # Convert the structured plan into target_files dicts, filtering invalid paths
    target_files = []
    for update in plan.updates:
        # Reject paths the LLM hallucinated (not in actual repo files)
        if update.doc_path not in existing_md_files:
            print(f"plan_updates: skipping hallucinated path '{update.doc_path}'")
            continue

        # Find the matching finding for context
        matched_finding = next(
            (
                f
                for f in drift_findings
                if update.doc_path in (f.get("matched_doc_paths") or [])
                or update.doc_path == f.get("doc_file_path")
            ),
            None,
        )

        target_files.append(
            {
                "doc_path": update.doc_path,
                "section": update.section,
                "action": update.action,
                "description": update.description,
                "finding": matched_finding or {},
            }
        )

    return {"target_files": target_files}
