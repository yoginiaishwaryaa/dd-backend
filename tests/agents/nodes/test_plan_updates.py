from unittest.mock import MagicMock, patch

from app.agents.nodes.plan_updates import plan_updates
from app.agents.state import DriftAnalysisState


# =========== Tests ===========


# Tests that empty findings return early with no target files.
def test_plan_updates_empty_findings():
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
    }

    with patch("app.agents.nodes.plan_updates._checkout_docs"):
        result = plan_updates(state)

    assert result == {"target_files": []}


# Tests that valid LLM output with real .md files produces target_files entries.
def test_plan_updates_returns_target_files(tmp_path):
    # Create a real .md file so the anti-hallucination scan finds it
    doc_file = tmp_path / "docs" / "api.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# API Docs", encoding="utf-8")

    mock_plan = MagicMock()
    mock_update = MagicMock()
    mock_update.doc_path = "docs/api.md"
    mock_update.section = "Authentication"
    mock_update.action = "update"
    mock_update.description = "Update auth endpoint docs"
    mock_plan.updates = [mock_update]

    mock_llm_instance = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = mock_plan
    mock_llm_instance.with_structured_output.return_value = mock_structured

    state: DriftAnalysisState = {
        "drift_event_id": "evt-1",
        "base_sha": "base",
        "head_sha": "head",
        "session": None,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": [],
        "style_preference": "professional",
        "findings": [
            {
                "code_path": "app/auth.py",
                "drift_type": "outdated_docs",
                "explanation": "Auth endpoint changed",
                "matched_doc_paths": ["docs/api.md"],
            }
        ],
        "repo_path": str(tmp_path),
        "target_files": [],
        "rewrite_results": [],
    }

    with (
        patch("app.agents.nodes.plan_updates._checkout_docs"),
        patch(
            "app.agents.llm.ChatGoogleGenerativeAI",
            return_value=mock_llm_instance,
        ),
    ):
        result = plan_updates(state)

    assert len(result["target_files"]) == 1
    assert result["target_files"][0]["doc_path"] == "docs/api.md"
    assert result["target_files"][0]["action"] == "update"


# Tests that an LLM error returns an empty target_files list instead of raising.
def test_plan_updates_llm_error_returns_empty():
    mock_llm_instance = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.side_effect = Exception("LLM error")
    mock_llm_instance.with_structured_output.return_value = mock_structured

    state: DriftAnalysisState = {
        "drift_event_id": "evt-1",
        "base_sha": "base",
        "head_sha": "head",
        "session": None,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": [],
        "style_preference": "professional",
        "findings": [
            {
                "code_path": "app/auth.py",
                "drift_type": "outdated_docs",
                "explanation": "Auth endpoint changed",
                "matched_doc_paths": ["docs/api.md"],
            }
        ],
        "repo_path": "/tmp/repos/owner/repo",
        "target_files": [],
        "rewrite_results": [],
    }

    with (
        patch("app.agents.nodes.plan_updates._checkout_docs"),
        patch(
            "app.agents.llm.ChatGoogleGenerativeAI",
            return_value=mock_llm_instance,
        ),
    ):
        result = plan_updates(state)

    assert result == {"target_files": []}
