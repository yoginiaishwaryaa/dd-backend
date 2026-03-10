from unittest.mock import patch

from app.agents.nodes.apply_changes import apply_changes
from app.agents.state import DriftAnalysisState


# =========== Tests ===========


# Tests that rewrite results are written to the correct paths on disk.
def test_apply_changes_writes_files(tmp_path):
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
        "target_files": [],
        "rewrite_results": [
            {
                "doc_path": "docs/api.md",
                "new_content": "# Updated API\nNew content here.",
            }
        ],
    }

    with patch("app.agents.nodes.apply_changes._commit_and_pr"):
        result = apply_changes(state)

    assert result == {}
    written = (tmp_path / "docs" / "api.md").read_text(encoding="utf-8")
    assert "Updated API" in written


# Tests that a path traversal attempt outside the repo root is blocked.
def test_apply_changes_blocks_path_traversal(tmp_path):
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
        "repo_path": str(tmp_path / "repo"),
        "target_files": [],
        "rewrite_results": [
            {
                "doc_path": "../../etc/passwd",
                "new_content": "malicious content",
            }
        ],
    }

    with patch("app.agents.nodes.apply_changes._commit_and_pr"):
        result = apply_changes(state)

    assert result == {}
    assert not (tmp_path / "etc" / "passwd").exists()


# Tests that non-markdown files in rewrite results are not written to disk.
def test_apply_changes_skips_non_markdown(tmp_path):
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
        "target_files": [],
        "rewrite_results": [
            {
                "doc_path": "app/main.py",
                "new_content": "import os",
            }
        ],
    }

    with patch("app.agents.nodes.apply_changes._commit_and_pr"):
        result = apply_changes(state)

    assert result == {}
    assert not (tmp_path / "app" / "main.py").exists()
