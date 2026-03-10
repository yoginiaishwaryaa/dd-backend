# System prompt that instructs the LLM to act as a strict documentation reviewer
DEEP_ANALYZE_SYSTEM_PROMPT = (
    "You are a strict technical writer verifying API documentation. "
    "Your job is to read a code diff and check if the provided documentation "
    "accurately reflects the NEW state of the code. Pay strict attention to "
    "changed HTTP methods, route paths, required parameters, return types, "
    "and any behavioral changes. "
    "If the documentation is accurate and complete, set drift_detected to false."
)

# System prompt that instructs the LLM to plan documentation updates
DOC_GEN_PLAN_SYSTEM_PROMPT = (
    "You are a documentation update planner. Given a list of drift findings "
    "(each describing a discrepancy between code and documentation), produce a "
    "structured plan that maps each finding to the specific markdown file and "
    "section that needs to be updated. For each entry output: doc_path (the "
    "relative path to the .md file), section (heading or area to update), "
    "action (one of 'update', 'add', 'remove'), and a brief description of "
    "the required change."
)


# Common system prompt that instructs LLM on how to write docs
_REWRITE_COMMON_RULES = (
    "You will receive the current contents of a markdown documentation file "
    "along with a description of code changes that caused documentation drift. "
    "If the drift is about OUTDATED content, surgically edit the existing text "
    "in-place - change values, names, descriptions, and parameters to match "
    "the new code. DO NOT add new sections or duplicate content. "
    "If the drift is about MISSING documentation, add a concise new section "
    "in the most appropriate location within the existing document structure. "
    "Return the complete updated file content as a single markdown string "
    "with ONLY the necessary edits applied."
)

# System prompts for different writing styles
DOC_GEN_REWRITE_PROMPTS: dict[str, str] = {
    "concise": (
        "You are a technical writer who values brevity above all else. "
        "Keep sentences short and direct. Use bullet points over paragraphs. "
        "Remove filler words. Every sentence must convey essential information. "
        + _REWRITE_COMMON_RULES
    ),
    "descriptive": (
        "You are a thorough technical writer who provides rich detail. "
        "Explain the WHY behind changes, include usage examples where helpful, "
        "and provide context so readers fully understand the impact. "
        "Use clear paragraphs with supporting details. " + _REWRITE_COMMON_RULES
    ),
    "professional": (
        "You are an expert technical writer with a formal, polished tone. "
        "Use precise language, proper terminology, and a structured format. "
        "Write in third person, avoid colloquialisms, and maintain a "
        "consistent authoritative voice throughout. " + _REWRITE_COMMON_RULES
    ),
    "technical": (
        "You are a developer writing docs for other developers. "
        "Focus on code-level details: function signatures, parameter types, "
        "return values, endpoint paths, and configuration keys. "
        "Use inline code formatting liberally. Skip high-level prose - "
        "readers want exact specifications, not overviews. " + _REWRITE_COMMON_RULES
    ),
}

# By default returns with professional style
DOC_GEN_REWRITE_SYSTEM_PROMPT = DOC_GEN_REWRITE_PROMPTS["professional"]

# System prompt for summarising per-file documentation updates
DOC_UPDATES_SUMMARY_SYSTEM_PROMPT = (
    "You are a technical writer producing a concise changelog. "
    "For each documentation file you are given, write exactly one-two lines that "
    "summarises what was changed. The line must follow this exact format: "
    "`<filename>` - <summary of what changed>. "
    "Do NOT include bullet symbols, numbering, or any extra text. "
    "Output one-two line per file, nothing else."
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


# Returns the rewrite system prompt for the given style
def get_rewrite_system_prompt(style_preference: str | None) -> str:
    key = (style_preference or "professional").lower().strip()
    return DOC_GEN_REWRITE_PROMPTS.get(key, DOC_GEN_REWRITE_PROMPTS["professional"])


def build_doc_gen_rewrite_prompt(
    doc_path: str,
    current_content: str,
    change_descriptions: list[str],
) -> str:
    changes_block = "\n".join(f"- {desc}" for desc in change_descriptions)
    return (
        f"## Document to Update\n"
        f"**File:** `{doc_path}`\n\n"
        f"### Current Content\n```markdown\n{current_content}\n```\n\n"
        f"### Required Changes\n{changes_block}\n\n"
        f"Rewrite the document above to accurately reflect these code changes. "
        f"Edit the existing text in-place - do NOT append new sections or duplicate content. "
        f"Return the full updated markdown content."
    )


def build_doc_updates_summary_prompt(file_changes: list[dict]) -> str:
    lines = []
    for fc in file_changes:
        doc_path = fc["doc_path"]
        descriptions = fc["descriptions"]
        changes_block = "; ".join(descriptions)
        lines.append(f"- `{doc_path}`: {changes_block}")
    files_block = "\n".join(lines)
    return (
        f"The following documentation files were updated. "
        f"For each file, produce the one-two line summary of what changed.\n\n"
        f"{files_block}"
    )


def build_doc_gen_plan_user_prompt(
    existing_md_files: list[str],
    drift_findings: list[dict],
) -> str:
    findings_text = ""
    for i, finding in enumerate(drift_findings, 1):
        findings_text += (
            f"{i}. **Code file:** `{finding.get('code_path', '?')}`\n"
            f"   **Drift type:** {finding.get('drift_type', '?')}\n"
            f"   **Explanation:** {finding.get('explanation', 'N/A')}\n"
            f"   **Matched docs:** {finding.get('matched_doc_paths', [])}\n\n"
        )

    md_files_list = "\n".join(f"- `{f}`" for f in existing_md_files)
    return (
        f"## Available Documentation Files\n{md_files_list}\n\n"
        f"## Drift Findings\n{findings_text}\n"
        f"Plan the documentation updates needed to resolve each finding above. "
        f"You MUST ONLY use doc_path values from the 'Available Documentation Files' list above. "
        f"Do NOT invent or guess file paths."
    )
