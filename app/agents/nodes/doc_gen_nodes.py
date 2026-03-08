from pathlib import Path
from typing import Any, cast
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.core.config import settings
from app.agents.state import DriftAnalysisState
from app.agents.prompts import (
    DOC_GEN_PLAN_SYSTEM_PROMPT,
    get_rewrite_system_prompt,
    build_doc_gen_rewrite_prompt,
)


# Structured output schema for the plan_updates LLM call
class PlannedUpdate(BaseModel):
    doc_path: str
    section: str
    action: str
    description: str


class UpdatePlan(BaseModel):
    updates: list[PlannedUpdate]


# Node analyses drift findings and maps them to specific doc files/sections
def plan_updates(state: DriftAnalysisState) -> dict[str, Any]:
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
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0,
    )
    structured_llm = llm.with_structured_output(UpdatePlan)

    # Build user prompt with all findings AND the list of real doc files
    findings_text = ""
    for i, finding in enumerate(drift_findings, 1):
        findings_text += (
            f"{i}. **Code file:** `{finding.get('code_path', '?')}`\n"
            f"   **Drift type:** {finding.get('drift_type', '?')}\n"
            f"   **Explanation:** {finding.get('explanation', 'N/A')}\n"
            f"   **Matched docs:** {finding.get('matched_doc_paths', [])}\n\n"
        )

    md_files_list = "\n".join(f"- `{f}`" for f in existing_md_files)

    user_prompt = (
        f"## Available Documentation Files\n{md_files_list}\n\n"
        f"## Drift Findings\n{findings_text}\n"
        f"Plan the documentation updates needed to resolve each finding above. "
        f"You MUST ONLY use doc_path values from the 'Available Documentation Files' list above. "
        f"Do NOT invent or guess file paths."
    )

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


# Node rewrites each target doc file using the LLM
def rewrite_docs(state: DriftAnalysisState) -> dict[str, Any]:
    target_files: list[dict] = state["target_files"]
    repo_path: str = state["repo_path"]
    style_preference: str = state.get("style_preference", "professional")

    if not target_files:
        return {"rewrite_results": []}

    # Initialise Gemini for rewriting
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.2,
    )

    rewrite_results: list[dict] = []

    # Group targets by doc_path so each file is rewritten once with all its changes
    grouped: dict[str, list[str]] = {}
    for target in target_files:
        doc_path = target["doc_path"]
        description = target.get("description", "")
        grouped.setdefault(doc_path, []).append(description)

    for doc_path, change_descriptions in grouped.items():
        # Read the current file content
        full_path = Path(repo_path) / doc_path

        # Security check: ensure the path is within the repo
        try:
            resolved = full_path.resolve()
            repo_resolved = Path(repo_path).resolve()
            if not str(resolved).startswith(str(repo_resolved)):
                print(f"SECURITY: Path traversal blocked for {doc_path}")
                continue
        except Exception:
            print(f"SECURITY: Could not resolve path {doc_path}")
            continue

        if not full_path.exists():
            print(f"Doc file not found: {full_path}")
            continue

        try:
            current_content = full_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"Error reading {full_path}: {exc}")
            continue

        user_prompt = build_doc_gen_rewrite_prompt(
            doc_path=doc_path,
            current_content=current_content,
            change_descriptions=change_descriptions,
        )

        try:
            result = llm.invoke(
                [
                    {"role": "system", "content": get_rewrite_system_prompt(style_preference)},
                    {"role": "user", "content": user_prompt},
                ]
            )
            new_content: str = str(result.content) if hasattr(result, "content") else str(result)

            # Strip markdown code fences if the LLM wrapped the output
            if new_content.startswith("```markdown"):
                new_content = new_content[len("```markdown") :].strip()
            if new_content.startswith("```"):
                new_content = new_content[3:].strip()
            if new_content.endswith("```"):
                new_content = new_content[:-3].strip()

            rewrite_results.append(
                {
                    "doc_path": doc_path,
                    "new_content": new_content,
                }
            )
        except Exception as exc:
            print(f"LLM error rewriting {doc_path}: {exc}")
            continue

    return {"rewrite_results": rewrite_results}


# Node writes the rewritten content to the local .md files
def apply_changes(state: DriftAnalysisState) -> dict[str, Any]:
    rewrite_results: list[dict] = state["rewrite_results"]
    repo_path: str = state["repo_path"]

    for result in rewrite_results:
        doc_path = result["doc_path"]
        new_content = result["new_content"]

        full_path = Path(repo_path) / doc_path

        # Security check: prevent path traversal outside the repo directory
        try:
            resolved = full_path.resolve()
            repo_resolved = Path(repo_path).resolve()
            if not str(resolved).startswith(str(repo_resolved)):
                print(f"SECURITY: Path traversal blocked for {doc_path}")
                continue
        except Exception:
            print(f"SECURITY: Could not resolve path {doc_path}")
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

    return {}
