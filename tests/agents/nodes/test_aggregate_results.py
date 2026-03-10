import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.nodes.aggregate_results import aggregate_results
from app.agents.state import DriftAnalysisState


# =========== Helper Functions ===========


# Helper function to build a minimal state dictionary
def _make_state(
    findings: list[dict] | None = None,
    change_elements: list[dict] | None = None,
    analysis_payloads: list[dict] | None = None,
    drift_event_id: str = "evt-1",
) -> DriftAnalysisState:
    return {
        "drift_event_id": drift_event_id,
        "base_sha": "abc123",
        "head_sha": "def456",
        "session": MagicMock(),
        "repo_path": "/tmp/repo",
        "docs_root_path": "/docs",
        "change_elements": change_elements or [],
        "analysis_payloads": analysis_payloads or [],
        "findings": findings or [],
        "target_files": [],
        "rewrite_results": [],
        "style_preference": "professional",
    }


# Helper function to create a mock DriftEvent with repository relationship.
def _make_drift_event(
    check_run_id=None, repo_name="owner/repo", installation_id=12345, pr_number=42
):
    repo = MagicMock()
    repo.repo_name = repo_name
    repo.installation_id = installation_id
    repo.installation = MagicMock()
    repo.installation.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    event = MagicMock()
    event.check_run_id = check_run_id
    event.pr_number = pr_number
    event.repository = repo
    return event


# =========== Tests ===========


# Tests that empty findings produce a clean result with score 0.0 and no DriftFinding rows.
def test_no_findings_clean():
    state = _make_state(findings=[])
    drift_event = _make_drift_event()
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with patch("app.agents.nodes.aggregate_results.create_notification"):
        result = aggregate_results(state)

    assert result == {"findings": []}

    # DriftEvent should be updated to clean
    assert drift_event.overall_drift_score == 0.0
    assert drift_event.drift_result == "clean"
    assert drift_event.processing_phase == "completed"
    assert "No documentation drift" in drift_event.summary

    # No DriftFinding rows should be added
    state["session"].add.assert_not_called()
    state["session"].commit.assert_called_once()


# Tests that findings present result in drift_detected and DriftFinding rows being created.
def test_drift_detected_persists_findings():
    findings = [
        {
            "code_path": "src/routes.py",
            "change_type": "modified",
            "drift_type": "outdated_docs",
            "drift_score": 0.85,
            "explanation": "Route /date renamed to /today",
            "confidence": 0.9,
        },
    ]
    state = _make_state(findings=findings)
    drift_event = _make_drift_event()
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with (
        patch("app.agents.nodes.aggregate_results.DriftFinding") as mock_finding_cls,
        patch("app.agents.nodes.aggregate_results.create_notification"),
    ):
        mock_finding_cls.return_value = MagicMock()
        result = aggregate_results(state)

    assert result == {"findings": []}
    assert drift_event.drift_result == "drift_detected"
    assert drift_event.overall_drift_score == 0.85
    assert drift_event.processing_phase == "completed"

    # Only one DriftFinding row should be staged
    state["session"].add.assert_called_once()


# Tests that a finding with missing_docs sets drift_result to 'missing_docs'.
def test_missing_docs_result():
    findings = [
        {
            "code_path": "src/new.py",
            "change_type": "added",
            "drift_type": "missing_docs",
            "drift_score": 1.0,
            "explanation": "New code has no docs",
            "confidence": 1.0,
        },
        {
            "code_path": "src/routes.py",
            "change_type": "modified",
            "drift_type": "outdated_docs",
            "drift_score": 0.7,
            "explanation": "Route changed",
            "confidence": 0.8,
        },
    ]
    state = _make_state(findings=findings)
    drift_event = _make_drift_event()
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with (
        patch("app.agents.nodes.aggregate_results.DriftFinding") as mock_finding_cls,
        patch("app.agents.nodes.aggregate_results.create_notification"),
    ):
        mock_finding_cls.return_value = MagicMock()
        aggregate_results(state)

    assert drift_event.drift_result == "missing_docs"
    assert drift_event.overall_drift_score == 1.0

    # Two DriftFinding rows should be staged
    assert state["session"].add.call_count == 2


# Test that when drift_event is not found, session.commit is still called and no exception raised
def test_drift_event_not_found_in_db_still_commits():
    state = _make_state(findings=[])

    # Simulating DriftEvent query returning None
    state["session"].query.return_value.filter.return_value.first.return_value = None

    result = aggregate_results(state)

    assert result == {"findings": []}
    state["session"].commit.assert_called_once()

    # No DriftFinding rows should be added
    state["session"].add.assert_not_called()


# Test that overall_drift_score is the maximum across all findings
def test_overall_drift_score_is_maximum():
    findings = [
        {
            "code_path": "src/a.py",
            "change_type": "modified",
            "drift_type": "outdated_docs",
            "drift_score": 0.5,
            "explanation": "Minor change",
            "confidence": 0.8,
        },
        {
            "code_path": "src/b.py",
            "change_type": "added",
            "drift_type": "missing_docs",
            "drift_score": 0.95,
            "explanation": "New code undocumented",
            "confidence": 1.0,
        },
    ]
    state = _make_state(findings=findings)
    drift_event = _make_drift_event()
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with (
        patch("app.agents.nodes.aggregate_results.DriftFinding"),
        patch("app.agents.nodes.aggregate_results.create_notification"),
    ):
        aggregate_results(state)

    assert drift_event.overall_drift_score == 0.95


# =========== Notifications Tests ===========


# Test notification content when result is clean
def test_notification_content_clean():
    state = _make_state(findings=[])
    drift_event = _make_drift_event()
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with patch("app.agents.nodes.aggregate_results.create_notification") as mock_notif:
        aggregate_results(state)

    mock_notif.assert_called_once()
    _, user_id_arg, content = mock_notif.call_args[0]
    assert user_id_arg == drift_event.repository.installation.user_id
    assert "PR #42" in content
    assert "owner/repo" in content
    assert "No documentation drift detected" in content


# Test notification content when documentation drift is detected
def test_notification_content_drift_detected():
    findings = [
        {
            "code_path": "src/api.py",
            "change_type": "modified",
            "drift_type": "outdated_docs",
            "drift_score": 0.75,
            "explanation": "Route changed",
            "confidence": 0.9,
        }
    ]
    state = _make_state(findings=findings)
    drift_event = _make_drift_event()
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with (
        patch("app.agents.nodes.aggregate_results.DriftFinding"),
        patch("app.agents.nodes.aggregate_results.create_notification") as mock_notif,
    ):
        aggregate_results(state)

    mock_notif.assert_called_once()
    _, user_id_arg, content = mock_notif.call_args[0]
    assert user_id_arg == drift_event.repository.installation.user_id
    assert "PR #42" in content
    assert "owner/repo" in content
    assert "Documentation drift detected" in content
    assert "0.75" in content


# Test notification content when missing docs drift is detected
def test_notification_content_missing_docs():
    findings = [
        {
            "code_path": "src/new.py",
            "change_type": "added",
            "drift_type": "missing_docs",
            "drift_score": 1.0,
            "explanation": "No docs",
            "confidence": 1.0,
        }
    ]
    state = _make_state(findings=findings)
    drift_event = _make_drift_event()
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with (
        patch("app.agents.nodes.aggregate_results.DriftFinding"),
        patch("app.agents.nodes.aggregate_results.create_notification") as mock_notif,
    ):
        aggregate_results(state)

    mock_notif.assert_called_once()
    _, user_id_arg, content = mock_notif.call_args[0]
    assert user_id_arg == drift_event.repository.installation.user_id
    assert "PR #42" in content
    assert "owner/repo" in content
    assert "Missing documentation detected" in content
    assert "1.00" in content


# Test no notification is sent when installation has no user_id
def test_notification_not_sent_when_no_user_id():
    state = _make_state(findings=[])
    drift_event = _make_drift_event()
    drift_event.repository.installation.user_id = None
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with patch("app.agents.nodes.aggregate_results.create_notification") as mock_notif:
        aggregate_results(state)

    mock_notif.assert_not_called()


# =========== GH Check Run Tests ===========


# Tests that when check_run_id exists, update_github_check_run is called.
@patch("app.agents.nodes.aggregate_results.update_github_check_run", new_callable=AsyncMock)
def test_check_run_updated(mock_update):
    findings = [
        {
            "code_path": "src/api.py",
            "change_type": "modified",
            "drift_type": "outdated_docs",
            "drift_score": 0.8,
            "explanation": "API changed",
            "confidence": 0.9,
        },
    ]
    state = _make_state(findings=findings)
    drift_event = _make_drift_event(check_run_id=999)
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with patch("app.agents.nodes.aggregate_results.DriftFinding") as mock_finding_cls:
        mock_finding_cls.return_value = MagicMock()
        aggregate_results(state)

    mock_update.assert_called_once()


# Tests that when there is no check_run_id, the update helper is not called.
@patch("app.agents.nodes.aggregate_results.update_github_check_run", new_callable=AsyncMock)
def test_check_run_skipped_when_none(mock_update):
    state = _make_state(findings=[])
    drift_event = _make_drift_event(check_run_id=None)
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    aggregate_results(state)

    mock_update.assert_not_called()


# Test that the check run conclusion is "success" when drift_result is "clean"
@patch("app.agents.nodes.aggregate_results.update_github_check_run", new_callable=AsyncMock)
def test_check_run_conclusion_success_when_clean(mock_update):
    state = _make_state(findings=[])
    drift_event = _make_drift_event(check_run_id=42)
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    aggregate_results(state)

    mock_update.assert_called_once()
    _, kwargs = mock_update.call_args
    assert kwargs["conclusion"] == "success"


# Test that the check run conclusion is "action_required" when drift is detected
@patch("app.agents.nodes.aggregate_results.update_github_check_run", new_callable=AsyncMock)
def test_check_run_conclusion_action_required_when_drift(mock_update):
    findings = [
        {
            "code_path": "src/api.py",
            "change_type": "modified",
            "drift_type": "outdated_docs",
            "drift_score": 0.9,
            "explanation": "Route changed",
            "confidence": 0.95,
        }
    ]
    state = _make_state(findings=findings)
    drift_event = _make_drift_event(check_run_id=42)
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    with patch("app.agents.nodes.aggregate_results.DriftFinding"):
        aggregate_results(state)

    mock_update.assert_called_once()
    _, kwargs = mock_update.call_args
    assert kwargs["conclusion"] == "action_required"


# Test that a check run update exception is caught and does not propagate
@patch("app.agents.nodes.aggregate_results.update_github_check_run", new_callable=AsyncMock)
def test_check_run_update_exception_is_swallowed(mock_update):
    mock_update.side_effect = Exception("GitHub API down")

    state = _make_state(findings=[])
    drift_event = _make_drift_event(check_run_id=99)
    state["session"].query.return_value.filter.return_value.first.return_value = drift_event

    # Should not raise even though update_github_check_run raises
    result = aggregate_results(state)

    assert result == {"findings": []}
