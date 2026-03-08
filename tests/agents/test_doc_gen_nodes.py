from unittest.mock import MagicMock, patch
from app.agents.nodes.doc_gen_nodes import plan_updates, rewrite_docs, apply_changes


# ----- plan_updates tests -----


def test_plan_updates_empty_findings():
    state = {
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

    result = plan_updates(state)

    assert result == {"target_files": []}


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

    state = {
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

    with patch(
        "app.agents.nodes.doc_gen_nodes.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = plan_updates(state)

    assert len(result["target_files"]) == 1
    assert result["target_files"][0]["doc_path"] == "docs/api.md"
    assert result["target_files"][0]["action"] == "update"


def test_plan_updates_llm_error_returns_empty():
    mock_llm_instance = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.side_effect = Exception("LLM error")
    mock_llm_instance.with_structured_output.return_value = mock_structured

    state = {
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

    with patch(
        "app.agents.nodes.doc_gen_nodes.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = plan_updates(state)

    assert result == {"target_files": []}


# ----- rewrite_docs tests -----


def test_rewrite_docs_empty_targets():
    state = {
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

    result = rewrite_docs(state)

    assert result == {"rewrite_results": []}


def test_rewrite_docs_rewrites_file(tmp_path):
    # Create a real temp markdown file
    doc_file = tmp_path / "docs" / "api.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# API\nOld content", encoding="utf-8")

    mock_llm_response = MagicMock()
    mock_llm_response.content = "# API\nUpdated content"

    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = mock_llm_response

    state = {
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
    }

    with patch(
        "app.agents.nodes.doc_gen_nodes.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = rewrite_docs(state)

    assert len(result["rewrite_results"]) == 1
    assert result["rewrite_results"][0]["doc_path"] == "docs/api.md"
    assert "Updated content" in result["rewrite_results"][0]["new_content"]


def test_rewrite_docs_strips_code_fences(tmp_path):
    doc_file = tmp_path / "docs" / "api.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# Old", encoding="utf-8")

    mock_llm_response = MagicMock()
    mock_llm_response.content = "```markdown\n# New Content\n```"

    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = mock_llm_response

    state = {
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
            {"doc_path": "docs/api.md", "section": "API", "action": "update", "description": "Update", "finding": {}}
        ],
        "rewrite_results": [],
    }

    with patch(
        "app.agents.nodes.doc_gen_nodes.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = rewrite_docs(state)

    # Code fences should be stripped
    assert not result["rewrite_results"][0]["new_content"].startswith("```")
    assert "# New Content" in result["rewrite_results"][0]["new_content"]


def test_rewrite_docs_blocks_path_traversal(tmp_path):
    # Create a file outside the repo
    doc_file = tmp_path / "docs" / "api.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text("# API", encoding="utf-8")

    mock_llm_instance = MagicMock()

    state = {
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
            {"doc_path": "../docs/api.md", "section": "API", "action": "update", "description": "Update", "finding": {}}
        ],
        "rewrite_results": [],
    }

    with patch(
        "app.agents.nodes.doc_gen_nodes.ChatGoogleGenerativeAI",
        return_value=mock_llm_instance,
    ):
        result = rewrite_docs(state)

    # Should be blocked — no results
    assert result == {"rewrite_results": []}


# ----- apply_changes tests -----


def test_apply_changes_writes_files(tmp_path):
    state = {
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

    result = apply_changes(state)

    assert result == {}
    written = (tmp_path / "docs" / "api.md").read_text(encoding="utf-8")
    assert "Updated API" in written


def test_apply_changes_blocks_path_traversal(tmp_path):
    state = {
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

    result = apply_changes(state)

    assert result == {}
    # File should NOT have been created
    assert not (tmp_path / "etc" / "passwd").exists()


def test_apply_changes_skips_non_markdown(tmp_path):
    state = {
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

    result = apply_changes(state)

    assert result == {}
    # Non-markdown file should NOT have been written
    assert not (tmp_path / "app" / "main.py").exists()
