from typing import Literal
from unittest.mock import patch, MagicMock

from app.agents.nodes.deep_analyze import (
    deep_analyze,
    LLMDriftFinding,
)
from app.agents.state import DriftAnalysisState


# Helper function to build a minimal state dictionary
def _make_state(
    analysis_payloads: list[dict] | None = None,
    repo_path: str = "/tmp/repo",
    base_sha: str = "abc123def4",
    head_sha: str = "def456abc7",
) -> DriftAnalysisState:
    return {
        "drift_event_id": "evt-1",
        "base_sha": base_sha,
        "head_sha": head_sha,
        "session": None,
        "repo_path": repo_path,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": analysis_payloads or [],
        "findings": [],
        "target_files": [],
        "rewrite_results": [],
        "style_preference": "professional",
    }


# Helper function to create a mock LLMDriftFinding response.
def _mock_drift_finding(drift_detected: bool, **kwargs) -> LLMDriftFinding:
    drift_type: Literal["outdated_docs", "missing_docs", "ambiguous_docs", ""] = (
        "outdated_docs" if drift_detected else ""
    )
    defaults = {
        "drift_detected": drift_detected,
        "drift_type": drift_type,
        "drift_score": 0.9 if drift_detected else 0.0,
        "explanation": "Route changed from /date to /today but docs still say /date."
        if drift_detected
        else "Docs are up to date.",
        "confidence": 0.95 if drift_detected else 0.9,
    }
    defaults.update(kwargs)
    return LLMDriftFinding(**defaults)


# Tests that no analysis payloads results in an immediate return with empty findings.
def test_empty_payloads_returns_empty():
    state = _make_state(analysis_payloads=[])

    result = deep_analyze(state)

    assert result == {"findings": []}


# Tests that when the LLM returns drift_detected=True, a finding dict is appended.
@patch("app.agents.nodes.deep_analyze._get_git_diff")
@patch("app.agents.nodes.deep_analyze.ChatGoogleGenerativeAI")
def test_drift_detected_produces_finding(mock_llm_class, mock_get_diff):
    mock_get_diff.return_value = "- @app.route('/date')\n+ @app.route('/today')"

    mock_structured = MagicMock()
    mock_structured.invoke.return_value = _mock_drift_finding(True)
    mock_llm_instance = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured
    mock_llm_class.return_value = mock_llm_instance

    state = _make_state(
        analysis_payloads=[
            {
                "code_path": "src/routes.py",
                "change_type": "modified",
                "elements": ["get_date", "/today"],
                "old_elements": ["get_date", "/date"],
                "matched_doc_snippets": "GET /date returns the current date.",
            },
        ],
    )

    result = deep_analyze(state)

    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["code_path"] == "src/routes.py"
    assert finding["change_type"] == "modified"
    assert finding["drift_type"] == "outdated_docs"
    assert finding["drift_score"] == 0.9
    assert finding["confidence"] == 0.95
    assert "Route changed" in finding["explanation"]


# Tests that when the LLM returns drift_detected=False, no findings are appended.
@patch("app.agents.nodes.deep_analyze._get_git_diff")
@patch("app.agents.nodes.deep_analyze.ChatGoogleGenerativeAI")
def test_no_drift_skipped(mock_llm_class, mock_get_diff):
    mock_get_diff.return_value = "- # old comment\n+ # new comment"

    mock_structured = MagicMock()
    mock_structured.invoke.return_value = _mock_drift_finding(False)
    mock_llm_instance = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured
    mock_llm_class.return_value = mock_llm_instance

    state = _make_state(
        analysis_payloads=[
            {
                "code_path": "src/utils.py",
                "change_type": "modified",
                "elements": ["helper_fn"],
                "old_elements": ["helper_fn"],
                "matched_doc_snippets": "The `helper_fn` processes data.",
            },
        ],
    )

    result = deep_analyze(state)

    assert result["findings"] == []


# Tests that when the git diff returns None, the payload is skipped.
@patch("app.agents.nodes.deep_analyze._get_git_diff")
def test_git_diff_error_handled(mock_get_diff):
    mock_get_diff.return_value = None

    state = _make_state(
        analysis_payloads=[
            {
                "code_path": "src/gone.py",
                "change_type": "deleted",
                "elements": [],
                "old_elements": ["OldClass"],
                "matched_doc_snippets": "The `OldClass` handles legacy.",
            },
        ],
    )

    result = deep_analyze(state)

    assert result["findings"] == []


# Tests that with two payloads where one has drift and one doesn't, only one finding is produced.
@patch("app.agents.nodes.deep_analyze._get_git_diff")
@patch("app.agents.nodes.deep_analyze.ChatGoogleGenerativeAI")
def test_multiple_payloads(mock_llm_class, mock_get_diff):
    mock_get_diff.return_value = "some diff content"

    drift_response = _mock_drift_finding(True)
    clean_response = _mock_drift_finding(False)

    mock_structured = MagicMock()
    mock_structured.invoke.side_effect = [drift_response, clean_response]
    mock_llm_instance = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured
    mock_llm_class.return_value = mock_llm_instance

    state = _make_state(
        analysis_payloads=[
            {
                "code_path": "src/api.py",
                "change_type": "modified",
                "elements": ["/users"],
                "old_elements": ["/people"],
                "matched_doc_snippets": "GET /people returns user list.",
            },
            {
                "code_path": "src/models.py",
                "change_type": "modified",
                "elements": ["User"],
                "old_elements": ["User"],
                "matched_doc_snippets": "The `User` model stores user data.",
            },
        ],
    )

    result = deep_analyze(state)

    assert len(result["findings"]) == 1
    assert result["findings"][0]["code_path"] == "src/api.py"


# Tests that when the LLM raises an exception, the payload is skipped without crashing.
@patch("app.agents.nodes.deep_analyze._get_git_diff")
@patch("app.agents.nodes.deep_analyze.ChatGoogleGenerativeAI")
def test_llm_exception_handled(mock_llm_class, mock_get_diff):
    mock_get_diff.return_value = "some diff"

    mock_structured = MagicMock()
    mock_structured.invoke.side_effect = Exception("API rate limit exceeded")
    mock_llm_instance = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured
    mock_llm_class.return_value = mock_llm_instance

    state = _make_state(
        analysis_payloads=[
            {
                "code_path": "src/api.py",
                "change_type": "modified",
                "elements": ["/users"],
                "old_elements": [],
                "matched_doc_snippets": "GET /users returns list.",
            },
        ],
    )

    result = deep_analyze(state)

    assert result["findings"] == []
