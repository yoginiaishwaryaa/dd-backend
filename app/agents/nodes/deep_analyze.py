import subprocess
from typing import Any, cast

from app.schemas import LLMDriftFinding
from app.agents.llm import get_llm
from app.agents.state import DriftAnalysisState
from app.agents.prompts import DEEP_ANALYZE_SYSTEM_PROMPT, build_deep_analyze_user_prompt


# Return git diff output for a specific file between commits
def _get_git_diff(repo_path: str, base_sha: str, head_sha: str, file_path: str) -> str | None:
    try:
        # Run the git diff command
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", base_sha, head_sha, "--", file_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return None


# Node sends each payload to the LLM for semantic drift analysis
def deep_analyze(state: DriftAnalysisState) -> dict[str, Any]:
    analysis_payloads: list[dict] = state["analysis_payloads"]
    repo_path: str = state["repo_path"]
    base_sha: str = state["base_sha"]
    head_sha: str = state["head_sha"]

    # Skip LLM calls if retrieve_docs found nothing to analyse
    if not analysis_payloads:
        return {"findings": []}

    # Initialise Gemini with structured output bound to LLMDriftFinding
    structured_llm = get_llm().with_structured_output(LLMDriftFinding)

    new_findings: list[dict] = []

    # Build the prompt with the diff and matched doc snippets
    for i, payload in enumerate(analysis_payloads, 1):
        code_path: str = payload["code_path"]
        change_type: str = payload["change_type"]
        elements: list[str] = payload.get("elements", [])
        old_elements: list[str] = payload.get("old_elements", [])
        matched_doc_snippets: str = payload.get("matched_doc_snippets", "")

        # Get the raw diff to include in the LLM prompt
        diff = _get_git_diff(repo_path, base_sha, head_sha, code_path)

        if diff is None:
            print("ERROR: Could not retrieve git diff")
            continue

        if not diff.strip():
            continue

        user_prompt = build_deep_analyze_user_prompt(
            code_path=code_path,
            change_type=change_type,
            elements=elements,
            old_elements=old_elements,
            diff=diff,
            matched_doc_snippets=matched_doc_snippets,
        )

        try:
            # Invoke the LLM
            raw_result = structured_llm.invoke(
                [
                    {"role": "system", "content": DEEP_ANALYZE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            result = cast(LLMDriftFinding, raw_result)
        except Exception as exc:
            print(f"LLM error on payload {i}/{len(analysis_payloads)}: {exc}")
            raise

        # Record findings where the LLM confirms actual drift
        if result.drift_detected:
            new_findings.append(
                {
                    "code_path": code_path,
                    "change_type": change_type,
                    "drift_type": result.drift_type,
                    "drift_score": result.drift_score,
                    "explanation": result.explanation,
                    "confidence": result.confidence,
                    "matched_doc_paths": payload.get("matched_doc_paths", []),
                }
            )

    return {"findings": new_findings}
