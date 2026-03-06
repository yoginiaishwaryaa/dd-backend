# System prompt that instructs the LLM to act as a strict documentation reviewer
DEEP_ANALYZE_SYSTEM_PROMPT = (
    "You are a strict technical writer verifying API documentation. "
    "Your job is to read a code diff and check if the provided documentation "
    "accurately reflects the NEW state of the code. Pay strict attention to "
    "changed HTTP methods, route paths, required parameters, return types, "
    "and any behavioral changes. "
    "If the documentation is accurate and complete, set drift_detected to false."
)


def build_deep_analyze_user_prompt(
    code_path: str,
    change_type: str,
    elements: list[str],
    old_elements: list[str],
    diff: str,
    matched_doc_snippets: str,
) -> str:
    return (
        f"## Code Change\n"
        f"**File:** `{code_path}` ({change_type})\n"
        f"**New elements:** {elements}\n"
        f"**Old elements:** {old_elements}\n\n"
        f"### Git Diff\n```diff\n{diff}\n```\n\n"
        f"### Current Documentation Snippets\n{matched_doc_snippets}\n\n"
        f"Analyze whether the documentation above accurately reflects the "
        f"NEW state of the code after this diff. Focus on any discrepancies."
    )
