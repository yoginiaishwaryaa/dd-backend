from unittest.mock import MagicMock, patch

from app.agents.nodes.rewrite_docs import rewrite_docs
from app.agents.state import DriftAnalysisState


# Tests that empty target_files returns early with no rewrite results.
def test_rewrite_docs_empty_targets():
    state: DriftAnalysisState = {
        "drift_event_id": "evt-1",
        "base_sha": "base",
        "head_sha": "head",
        "session": None,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": [],
        "style_preference": "professional",
        "findings": [],
        "repo_path": "/tmp/repos/owner/repo",
        "target_files": [],
        "rewrite_results": [],
        "doc_updates_summary": "",
    }

    result = rewrite_docs(state)

    assert result == {"rewrite_results": []}


# Tests that a valid target file is rewritten with the LLM response content.
def test_rewrite_docs_rewrites_file(tmp_path):
    doc_file = tmp_path / "docs" / "api.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# API\nOld content", encoding="utf-8")

    mock_llm_response = MagicMock()
    mock_llm_response.content = "# API\nUpdated content"

    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = mock_llm_response

    state: DriftAnalysisState = {
        "drift_event_id": "evt-1",
        "base_sha": "base",
        "head_sha": "head",
        "session": None,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": [],
        "style_preference": "professional",
        "findings": [],
        "repo_path": str(tmp_path),
        "target_files": [
            {
                "doc_path": "docs/api.md",
                "section": "API",
                "action": "update",
                "description": "Update auth endpoint",
                "finding": {},
            }
        ],
        "rewrite_results": [],
        "doc_updates_summary": "",
    }

    with patch(
        "app.agents.llm.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = rewrite_docs(state)

    assert len(result["rewrite_results"]) == 1
    assert result["rewrite_results"][0]["doc_path"] == "docs/api.md"
    assert "Updated content" in result["rewrite_results"][0]["new_content"]


# Tests that markdown code fences wrapping the LLM output are stripped.
def test_rewrite_docs_strips_code_fences(tmp_path):
    doc_file = tmp_path / "docs" / "api.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# Old", encoding="utf-8")

    mock_llm_response = MagicMock()
    mock_llm_response.content = "```markdown\n# New Content\n```"

    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = mock_llm_response

    state: DriftAnalysisState = {
        "drift_event_id": "evt-1",
        "base_sha": "base",
        "head_sha": "head",
        "session": None,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": [],
        "style_preference": "professional",
        "findings": [],
        "repo_path": str(tmp_path),
        "target_files": [
            {
                "doc_path": "docs/api.md",
                "section": "API",
                "action": "update",
                "description": "Update",
                "finding": {},
            }
        ],
        "rewrite_results": [],
        "doc_updates_summary": "",
    }

    with patch(
        "app.agents.llm.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = rewrite_docs(state)

    assert not result["rewrite_results"][0]["new_content"].startswith("```")
    assert "# New Content" in result["rewrite_results"][0]["new_content"]


# Tests that a path traversal attempt outside the repo root is blocked.
def test_rewrite_docs_blocks_path_traversal(tmp_path):
    doc_file = tmp_path / "docs" / "api.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# API", encoding="utf-8")

    mock_llm_instance = MagicMock()

    state: DriftAnalysisState = {
        "drift_event_id": "evt-1",
        "base_sha": "base",
        "head_sha": "head",
        "session": None,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": [],
        "style_preference": "professional",
        "findings": [],
        "repo_path": str(tmp_path / "repo"),  # repo is a subdir
        "target_files": [
            {
                "doc_path": "../docs/api.md",
                "section": "API",
                "action": "update",
                "description": "Update",
                "finding": {},
            }
        ],
        "rewrite_results": [],
        "doc_updates_summary": "",
    }

    with patch(
        "app.agents.llm.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = rewrite_docs(state)

    assert result == {"rewrite_results": [], "doc_updates_summary": ""}
