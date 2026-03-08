import textwrap

from app.agents.nodes.retrieve_docs import retrieve_docs
from app.agents.state import DriftAnalysisState


# Helper function to build a minimal state dictionary
def _make_state(
    change_elements: list[dict] | None = None,
    repo_path: str = "/tmp/repo",
    docs_root_path: str = "/docs",
) -> DriftAnalysisState:
    return {
        "drift_event_id": "evt-1",
        "base_sha": "abc123def4",
        "head_sha": "def456abc7",
        "session": None,
        "repo_path": repo_path,
        "docs_root_path": docs_root_path,
        "change_elements": change_elements or [],
        "analysis_payloads": [],
        "findings": [],
        "target_files": [],
        "rewrite_results": [],
        "style_preference": "professional",
    }


# Tests that an added file with no doc mentions produces a missing_docs finding.
def test_fast_track_missing_docs(tmp_path):
    (tmp_path / "docs").mkdir()

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/new_module.py",
                "change_type": "added",
                "elements": ["NewClass", "helper_fn"],
                "old_elements": [],
            },
        ],
    )

    result = retrieve_docs(state)

    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["code_path"] == "src/new_module.py"
    assert finding["drift_type"] == "missing_docs"
    assert finding["drift_score"] == 1.0
    assert finding["confidence"] == 1.0
    assert "NewClass" in finding["explanation"]
    assert result["analysis_payloads"] == []


# Tests that an added file whose elements are mentioned in docs produces a payload.
def test_added_with_matches_no_finding(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "api.md").write_text("## API\n\nThe `NewClass` handles user creation.\n")

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/new_module.py",
                "change_type": "added",
                "elements": ["NewClass"],
                "old_elements": [],
            },
        ],
    )

    result = retrieve_docs(state)

    assert result["findings"] == []
    assert len(result["analysis_payloads"]) == 1
    payload = result["analysis_payloads"][0]
    assert payload["code_path"] == "src/new_module.py"
    assert "NewClass" in payload["matched_doc_snippets"]


# Tests that a modified file with an element found in docs produces an analysis payload with a snippet.
def test_matched_docs_produce_payload(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_content = textwrap.dedent("""\
        # Tax Module

        The `calculate_tax` function computes tax based on
        the user's income bracket and filing status.

        ## Usage

        Call `calculate_tax(income, status)` to get the result.
    """)
    (docs_dir / "tax.md").write_text(doc_content)

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/tax.py",
                "change_type": "modified",
                "elements": ["calculate_tax"],
                "old_elements": ["calculate_tax"],
            },
        ],
    )

    result = retrieve_docs(state)

    assert result["findings"] == []
    assert len(result["analysis_payloads"]) == 1
    payload = result["analysis_payloads"][0]
    assert payload["code_path"] == "src/tax.py"
    assert payload["change_type"] == "modified"
    assert payload["elements"] == ["calculate_tax"]
    assert "calculate_tax" in payload["matched_doc_snippets"]


# Tests that when some elements match docs and some don't, a single payload with all elements is produced.
def test_multiple_elements_partial_match(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("Use `existing_fn` for data processing.\n")

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/utils.py",
                "change_type": "modified",
                "elements": ["existing_fn", "brand_new_fn"],
                "old_elements": ["existing_fn"],
            },
        ],
    )

    result = retrieve_docs(state)

    assert len(result["analysis_payloads"]) == 1
    payload = result["analysis_payloads"][0]
    assert payload["elements"] == ["existing_fn", "brand_new_fn"]
    assert "existing_fn" in payload["matched_doc_snippets"]


# Tests that a deleted file whose old_elements appear in docs produces a payload for LLM analysis.
def test_deleted_files_with_docs(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "ref.md").write_text("The `OldClass` was used for legacy support.\n")

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/legacy.py",
                "change_type": "deleted",
                "elements": [],
                "old_elements": ["OldClass"],
            },
        ],
    )

    result = retrieve_docs(state)

    assert len(result["analysis_payloads"]) == 1
    assert result["analysis_payloads"][0]["change_type"] == "deleted"
    assert "OldClass" in result["analysis_payloads"][0]["matched_doc_snippets"]


# Tests that a renamed route not in docs but whose old name is in docs produces an LLM payload.
def test_renamed_route_found_via_old_elements(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "api.md").write_text("## API\n\n`GET /date` returns the current date.\n")

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/routes.py",
                "change_type": "modified",
                "elements": ["get_date", "/today"],
                "old_elements": ["get_date", "/date"],
            },
        ],
    )

    result = retrieve_docs(state)

    # The old route '/date' matches the docs so it should produce a payload
    assert result["findings"] == []
    assert len(result["analysis_payloads"]) == 1
    payload = result["analysis_payloads"][0]
    assert payload["code_path"] == "src/routes.py"
    assert "/date" in payload["matched_doc_snippets"]
    assert payload["old_elements"] == ["get_date", "/date"]


# Tests that when neither old nor new elements are found in docs, an outdated_docs finding is produced.
def test_modified_neither_old_nor_new_in_docs(tmp_path):
    (tmp_path / "docs").mkdir()

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/routes.py",
                "change_type": "modified",
                "elements": ["/today", "get_date"],
                "old_elements": ["/yesterday", "get_date_old"],
            },
        ],
    )

    result = retrieve_docs(state)

    assert len(result["findings"]) == 1
    assert result["findings"][0]["drift_type"] == "outdated_docs"
    assert result["analysis_payloads"] == []


# Tests that a modified file with no extractable code elements falls back to the filename stem as a search term
def test_empty_elements_falls_back_to_filename_stem(tmp_path):
    (tmp_path / "docs").mkdir()

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/empty.py",
                "change_type": "modified",
                "elements": [],
                "old_elements": [],
            },
        ],
    )

    result = retrieve_docs(state)

    # The file should not be silently skipped
    assert len(result["findings"]) == 1
    assert result["findings"][0]["code_path"] == "src/empty.py"
    assert result["findings"][0]["drift_type"] == "outdated_docs"
    assert result["analysis_payloads"] == []


# Tests that when the docs directory doesn't exist added code is marked with missing_docs.
def test_missing_docs_dir(tmp_path):
    state = _make_state(
        repo_path=str(tmp_path),
        docs_root_path="/nonexistent_docs",
        change_elements=[
            {
                "file_path": "src/app.py",
                "change_type": "added",
                "elements": ["App"],
                "old_elements": [],
            },
        ],
    )

    result = retrieve_docs(state)

    assert len(result["findings"]) == 1
    assert result["findings"][0]["drift_type"] == "missing_docs"


# Tests that a modified file with no doc matches produces an outdated_docs finding.
def test_modified_zero_matches_outdated_docs(tmp_path):
    (tmp_path / "docs").mkdir()

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/routes.py",
                "change_type": "modified",
                "elements": ["/today", "get_date"],
                "old_elements": [],
            },
        ],
    )

    result = retrieve_docs(state)

    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["drift_type"] == "outdated_docs"
    assert finding["drift_score"] == 0.8


# Tests that a deleted file with no doc matches is silently skipped.
def test_deleted_zero_matches_skipped(tmp_path):
    (tmp_path / "docs").mkdir()

    state = _make_state(
        repo_path=str(tmp_path),
        change_elements=[
            {
                "file_path": "src/old.py",
                "change_type": "deleted",
                "elements": [],
                "old_elements": ["OldThing"],
            },
        ],
    )

    result = retrieve_docs(state)

    assert result["findings"] == []
    assert result["analysis_payloads"] == []
