import os
import re
from typing import Any

from app.agents.state import DriftAnalysisState

# Number of lines above and below a match to include in a snippet for context
_CONTEXT_LINES = 15


# Recursively loads all markdown files from the docs directory
def _load_markdown_files(docs_dir: str) -> dict[str, str]:
    docs: dict[str, str] = {}

    if not os.path.isdir(docs_dir):
        return docs

    for root, _dirs, files in os.walk(docs_dir):
        for fname in files:
            # Get all .md files
            if not fname.endswith(".md"):
                continue
            abs_path = os.path.join(root, fname)
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    docs[abs_path] = f.read()
            except OSError:
                continue

    return docs


# Returns a section of content around the first line that mentions the element
def _extract_snippet(content: str, element: str, context_lines: int = _CONTEXT_LINES) -> str:
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if element in line:
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)
            return "\n".join(lines[start:end])
    return ""


# Node searches documentation for references to changed code elements
def retrieve_docs(state: DriftAnalysisState) -> dict[str, Any]:
    change_elements: list[dict] = state["change_elements"]
    repo_path: str = state["repo_path"]
    docs_root_path: str = state["docs_root_path"]

    new_findings: list[dict] = []
    new_payloads: list[dict] = []

    docs_dir = os.path.join(repo_path, docs_root_path.lstrip("/"))
    doc_files = _load_markdown_files(docs_dir)

    # For each changed file, search docs for any matching element names
    for i, ce in enumerate(change_elements, 1):
        file_path: str = ce["file_path"]
        change_type: str = ce["change_type"]
        elements: list[str] = ce["elements"]
        old_elements: list[str] = ce.get("old_elements", [])

        # Combine current and old elements to find renamed identifiers
        search_terms: set[str] = set(elements + old_elements)

        if not search_terms:
            continue

        matched_snippets: dict[str, list[str]] = {}

        # Use prefix anchored regex for routes, word-boundary regex for identifiers
        for term in search_terms:
            if term.startswith("/"):
                pattern = re.compile(re.escape(term) + r"(?:\b|$)")
            else:
                pattern = re.compile(r"\b" + re.escape(term) + r"\b")
            for doc_path, doc_content in doc_files.items():
                if pattern.search(doc_content):
                    snippet = _extract_snippet(doc_content, term)
                    if snippet:
                        matched_snippets.setdefault(doc_path, []).append(snippet)

        # Skip rest of the code for obvious findings that don't need LLM analysis
        total_matches = sum(len(s) for s in matched_snippets.values())
        if change_type == "added" and total_matches == 0:
            new_findings.append(
                {
                    "code_path": file_path,
                    "change_type": "added",
                    "drift_type": "missing_docs",
                    "drift_score": 1.0,
                    "explanation": f"Added code elements {elements} are not mentioned in any documentation.",
                    "confidence": 1.0,
                }
            )
            continue

        if change_type == "modified" and total_matches == 0:
            new_findings.append(
                {
                    "code_path": file_path,
                    "change_type": "modified",
                    "drift_type": "outdated_docs",
                    "drift_score": 0.8,
                    "explanation": f"Modified code elements (including {elements}) were not found in any documentation. They may have been renamed or are undocumented.",
                    "confidence": 0.8,
                }
            )
            continue

        # Elements that need LLM analysis
        if total_matches == 0:
            continue
        combined_snippets = "\n\n---\n\n".join(
            f"[{doc_path}]\n{chr(10).join(snippets)}"
            for doc_path, snippets in matched_snippets.items()
        )

        new_payloads.append(
            {
                "code_path": file_path,
                "change_type": change_type,
                "elements": elements,
                "old_elements": old_elements,
                "matched_doc_paths": list(matched_snippets.keys()),
                "matched_doc_snippets": combined_snippets,
            }
        )

    return {"findings": new_findings, "analysis_payloads": new_payloads}
