import pytest
import subprocess
from unittest.mock import MagicMock, patch
from pathlib import Path
from uuid import uuid4

from app.services.drift_analysis import _extract_and_save_code_changes, run_drift_analysis


# Helper to create a mock drift event with repository info
def _make_drift_event(
    base_sha="abc123",
    head_sha="def456",
    repo_name="owner/repo",
    file_ignore_patterns=None,
):
    drift_event = MagicMock()
    drift_event.id = uuid4()
    drift_event.base_sha = base_sha
    drift_event.head_sha = head_sha
    drift_event.repository.repo_name = repo_name
    drift_event.repository.file_ignore_patterns = file_ignore_patterns
    return drift_event


# Test extracting code changes with added, modified, and deleted files
def test_extract_and_save_code_changes_success():
    drift_event = _make_drift_event()
    session = MagicMock()

    # 3 Changed Files
    git_diff_output = "A\tsrc/new_file.py\nM\tsrc/existing.py\nD\tsrc/removed.py\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    # This should add 3 CodeChange records
    assert session.add.call_count == 3
    session.commit.assert_called_once()

    # Verify the change types recorded
    added_changes = [c.args[0] for c in session.add.call_args_list]
    change_types = [c.change_type for c in added_changes]
    assert change_types == ["added", "modified", "deleted"]


# Test code vs non code file detection in code changes
def test_extract_and_save_code_changes_is_code_detection():
    drift_event = _make_drift_event()
    session = MagicMock()

    # 4 Changed Files with different types
    git_diff_output = "A\tsrc/main.py\nA\tREADME.md\nA\timage.png\nA\tsrc/utils.js\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    assert session.add.call_count == 4

    added_changes = [c.args[0] for c in session.add.call_args_list]
    is_code_flags = {c.file_path: c.is_code for c in added_changes}

    assert is_code_flags["src/main.py"] is True
    assert is_code_flags["README.md"] is False
    assert is_code_flags["image.png"] is False
    assert is_code_flags["src/utils.js"] is True


# Test with empty git diff output (no changes should be detected)
def test_extract_and_save_code_changes_empty_diff():
    drift_event = _make_drift_event()
    session = MagicMock()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    session.add.assert_not_called()
    session.commit.assert_called_once()


# Test raises exception when local repository doesn't exist
def test_extract_and_save_code_changes_repo_not_found():
    drift_event = _make_drift_event()
    session = MagicMock()

    with patch("app.services.drift_analysis.get_local_repo_path") as mock_path:
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=False))

        with pytest.raises(Exception, match="Local repository not found"):
            _extract_and_save_code_changes(session, drift_event)


# Test raises exception when git diff command fails
def test_extract_and_save_code_changes_git_diff_failure():
    drift_event = _make_drift_event()
    session = MagicMock()

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "fatal: bad revision"

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        with pytest.raises(Exception, match="Git diff failed"):
            _extract_and_save_code_changes(session, drift_event)

    session.rollback.assert_called_once()


# Test raises exception on subprocess timeout
def test_extract_and_save_code_changes_timeout():
    drift_event = _make_drift_event()
    session = MagicMock()

    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 60)),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        with pytest.raises(Exception, match="Timeout while extracting code changes"):
            _extract_and_save_code_changes(session, drift_event)


# Test unknown git status code defaults to "modified"
def test_extract_and_save_code_changes_unknown_status():
    drift_event = _make_drift_event()
    session = MagicMock()

    git_diff_output = "R\tsrc/renamed.py\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    added_change = session.add.call_args_list[0].args[0]
    assert added_change.change_type == "modified"


# Test malformed git diff line (insufficient parts) is skipped
def test_extract_and_save_code_changes_skips_malformed_lines():
    drift_event = _make_drift_event()
    session = MagicMock()

    git_diff_output = "A\tsrc/valid.py\nmalformed_line\n\nA\tsrc/other.py\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    # Only 2 valid lines should produce CodeChange records
    assert session.add.call_count == 2


# Test that correct git command is constructed with base and head SHAs
def test_extract_and_save_code_changes_correct_git_command():
    drift_event = _make_drift_event(
        base_sha="sha_base", head_sha="sha_head", repo_name="org/project"
    )
    session = MagicMock()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_repo_path = MagicMock(spec=Path, exists=MagicMock(return_value=True))
        mock_path.return_value = mock_repo_path

        _extract_and_save_code_changes(session, drift_event)

    args = mock_run.call_args[0][0]
    assert args[0] == "git"
    assert args[1] == "-C"
    assert args[2] == str(mock_repo_path)
    assert args[3] == "diff"
    assert args[4] == "--name-status"
    assert args[5] == "sha_base...sha_head"


# Helper to set up a mock session with a drift event
def _setup_run_mocks(drift_event_id=None, docs_root_path="/docs"):
    drift_event_id = drift_event_id or str(uuid4())

    drift_event = MagicMock()
    drift_event.id = drift_event_id
    drift_event.repository.repo_name = "owner/repo"
    drift_event.repository.installation_id = 99
    drift_event.repository.docs_root_path = docs_root_path
    drift_event.check_run_id = 12345
    drift_event.processing_phase = "queued"
    drift_event.drift_result = "pending"

    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = drift_event

    return session, drift_event


# Test run_drift_analysis when drift event is not found
def test_run_drift_analysis_event_not_found():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None

    with patch("app.services.drift_analysis._create_session", return_value=session):
        run_drift_analysis("nonexistent-id")

    session.close.assert_called_once()


# Test run_drift_analysis always closes the session even on error
def test_run_drift_analysis_session_closed_on_error():
    session, drift_event = _setup_run_mocks()

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis.get_local_repo_path",
            side_effect=RuntimeError("boom"),
        ),
    ):
        with pytest.raises(RuntimeError):
            run_drift_analysis(str(drift_event.id))

    session.rollback.assert_called_once()
    session.close.assert_called_once()


# Test run_drift_analysis sets analyzing phase
def test_run_drift_analysis_sets_analyzing_phase():
    session, drift_event = _setup_run_mocks()
    phase_at_commit = []

    original_commit = session.commit

    def capture_phase():
        phase_at_commit.append(drift_event.processing_phase)
        original_commit()

    session.commit = capture_phase

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
        patch("app.services.drift_analysis._extract_and_save_code_changes"),
        patch("app.services.drift_analysis.drift_analysis_graph") as mock_graph,
    ):
        mock_path.return_value = Path("/repos/owner/repo")
        mock_graph.invoke.return_value = {"change_elements": [], "findings": []}

        run_drift_analysis(str(drift_event.id))

    # At commit time, phase should be "analyzing"
    assert phase_at_commit[0] == "analyzing"


# Test run_drift_analysis builds initial state with correct values
def test_run_drift_analysis_builds_initial_state():
    session, drift_event = _setup_run_mocks(docs_root_path="/documentation")
    drift_event.id = "test-event-id"
    drift_event.base_sha = "base123"
    drift_event.head_sha = "head456"

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
        patch("app.services.drift_analysis._extract_and_save_code_changes"),
        patch("app.services.drift_analysis.drift_analysis_graph") as mock_graph,
    ):
        mock_path.return_value = Path("/repos/owner/repo")
        mock_graph.invoke.return_value = {"change_elements": [], "findings": []}

        run_drift_analysis(str(drift_event.id))

        # Verify get_local_repo_path was called with the repo name
        mock_path.assert_called_once_with("owner/repo")

        # Verify the initial state passed to the graph has all correct values
        invoked_state = mock_graph.invoke.call_args[0][0]
        assert invoked_state["drift_event_id"] == "test-event-id"
        assert invoked_state["base_sha"] == "base123"
        assert invoked_state["head_sha"] == "head456"
        assert invoked_state["session"] is session
        assert invoked_state["repo_path"] == str(Path("/repos/owner/repo"))
        assert invoked_state["docs_root_path"] == "/documentation"
        assert invoked_state["change_elements"] == []
        assert invoked_state["analysis_payloads"] == []
        assert invoked_state["findings"] == []


# Test files matching an ignore pattern are saved with is_ignored=True
def test_extract_and_save_code_changes_ignores_pattern_match():
    drift_event = _make_drift_event(file_ignore_patterns=["tests/*", "*.lock"])
    session = MagicMock()

    git_diff_output = "A\tsrc/main.py\nA\ttests/test_main.py\nA\tpoetry.lock\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    added_changes = [c.args[0] for c in session.add.call_args_list]
    is_ignored_flags = {c.file_path: c.is_ignored for c in added_changes}

    assert is_ignored_flags["src/main.py"] is False
    assert is_ignored_flags["tests/test_main.py"] is True
    assert is_ignored_flags["poetry.lock"] is True


# Test files not matching any pattern are saved with is_ignored=False
def test_extract_and_save_code_changes_no_match_not_ignored():
    drift_event = _make_drift_event(file_ignore_patterns=["migrations/*"])
    session = MagicMock()

    git_diff_output = "M\tsrc/api.py\nM\tsrc/models.py\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    added_changes = [c.args[0] for c in session.add.call_args_list]
    assert all(c.is_ignored is False for c in added_changes)


# Test with no ignore patterns set (None), all files should be is_ignored=False
def test_extract_and_save_code_changes_no_ignore_patterns():
    drift_event = _make_drift_event(file_ignore_patterns=None)
    session = MagicMock()

    git_diff_output = "A\tsrc/app.py\nA\ttests/test_app.py\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    added_changes = [c.args[0] for c in session.add.call_args_list]
    assert all(c.is_ignored is False for c in added_changes)


# Helper functio to set up mocks specifically for failure-path tests in run_drift_analysis
def _setup_failure_mocks(check_run_id=12345):
    drift_event_id = str(uuid4())

    drift_event = MagicMock()
    drift_event.id = drift_event_id
    drift_event.pr_number = 42
    drift_event.check_run_id = check_run_id
    drift_event.repository.repo_name = "owner/repo"
    drift_event.repository.installation_id = 99
    drift_event.repository.docs_root_path = "/docs"
    drift_event.repository.installation.user_id = uuid4()

    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = drift_event

    return session, drift_event, drift_event_id


# Test that failure marks the drift event phase, result and error message
def test_run_drift_analysis_failure_marks_event_as_failed():
    session, drift_event, drift_event_id = _setup_failure_mocks()

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=RuntimeError("something broke"),
        ),
        patch("app.services.drift_analysis.asyncio.run"),
        patch("app.services.drift_analysis.update_github_check_run", new_callable=MagicMock),
        patch("app.services.drift_analysis.create_notification"),
    ):
        with pytest.raises(RuntimeError):
            run_drift_analysis(drift_event_id)

    assert drift_event.processing_phase == "failed"
    assert drift_event.drift_result == "error"
    assert "something broke" in drift_event.error_message


# Test that failure re-raises the original exception after cleanup
def test_run_drift_analysis_failure_reraises_exception():
    session, drift_event, drift_event_id = _setup_failure_mocks()

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=ValueError("critical failure"),
        ),
        patch("app.services.drift_analysis.asyncio.run"),
        patch("app.services.drift_analysis.update_github_check_run", new_callable=MagicMock),
        patch("app.services.drift_analysis.create_notification"),
    ):
        with pytest.raises(ValueError, match="critical failure"):
            run_drift_analysis(drift_event_id)


# Test that failure rolls back and then commits after cleanup
def test_run_drift_analysis_failure_rollback_then_commit():
    session, drift_event, drift_event_id = _setup_failure_mocks()

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=RuntimeError("something broke"),
        ),
        patch("app.services.drift_analysis.asyncio.run"),
        patch("app.services.drift_analysis.update_github_check_run", new_callable=MagicMock),
        patch("app.services.drift_analysis.create_notification"),
    ):
        with pytest.raises(RuntimeError):
            run_drift_analysis(drift_event_id)

    session.rollback.assert_called_once()
    # First commit sets "analyzing", second commit is the failure cleanup
    assert session.commit.call_count == 2


# Test that failure calls update_github_check_run with the correct failure args
def test_run_drift_analysis_failure_updates_check_run():
    session, drift_event, drift_event_id = _setup_failure_mocks(check_run_id=99999)

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=RuntimeError("crash"),
        ),
        patch("app.services.drift_analysis.asyncio.run") as mock_asyncio_run,
        patch(
            "app.services.drift_analysis.update_github_check_run", new_callable=MagicMock
        ) as mock_update_check_run,
        patch("app.services.drift_analysis.create_notification"),
    ):
        with pytest.raises(RuntimeError):
            run_drift_analysis(drift_event_id)

    mock_update_check_run.assert_called_once_with(
        repo_full_name="owner/repo",
        check_run_id=99999,
        installation_id=99,
        status="completed",
        conclusion="failure",
        title="Delta Drift Analysis",
        summary="Drift analysis failed due to an internal error.",
    )
    mock_asyncio_run.assert_called_once()


# Test that check run is NOT updated when check_run_id is None
def test_run_drift_analysis_failure_skips_check_run_when_no_id():
    session, drift_event, drift_event_id = _setup_failure_mocks(check_run_id=None)

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=RuntimeError("crash"),
        ),
        patch("app.services.drift_analysis.asyncio.run") as mock_asyncio_run,
        patch(
            "app.services.drift_analysis.update_github_check_run", new_callable=MagicMock
        ) as mock_update_check_run,
        patch("app.services.drift_analysis.create_notification"),
    ):
        with pytest.raises(RuntimeError):
            run_drift_analysis(drift_event_id)

    mock_update_check_run.assert_not_called()
    mock_asyncio_run.assert_not_called()


# Test that a failing check run update doesn't block the rest of failure cleanup
def test_run_drift_analysis_failure_check_run_error_doesnt_break_cleanup():
    session, drift_event, drift_event_id = _setup_failure_mocks(check_run_id=12345)

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=RuntimeError("crash"),
        ),
        patch(
            "app.services.drift_analysis.asyncio.run",
            side_effect=Exception("GitHub API down"),
        ),
        patch("app.services.drift_analysis.update_github_check_run", new_callable=MagicMock),
        patch("app.services.drift_analysis.create_notification"),
    ):
        with pytest.raises(RuntimeError, match="crash"):
            run_drift_analysis(drift_event_id)

    # Event should still be marked as failed and session committed
    assert drift_event.processing_phase == "failed"
    assert drift_event.drift_result == "error"
    session.commit.assert_called()


# Test notification is sent on failure with the correct content
def test_run_drift_analysis_failure_sends_notification():
    session, drift_event, drift_event_id = _setup_failure_mocks()
    user_id = drift_event.repository.installation.user_id

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=RuntimeError("something broke"),
        ),
        patch("app.services.drift_analysis.asyncio.run"),
        patch("app.services.drift_analysis.update_github_check_run", new_callable=MagicMock),
        patch("app.services.drift_analysis.create_notification") as mock_notif,
    ):
        with pytest.raises(RuntimeError):
            run_drift_analysis(drift_event_id)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "PR #42" in content
    assert "owner/repo" in content
    assert "failed" in content


# Test no notification is sent when installation has no user_id
def test_run_drift_analysis_failure_no_notification_when_no_user_id():
    session, drift_event, drift_event_id = _setup_failure_mocks()
    drift_event.repository.installation.user_id = None

    with (
        patch("app.services.drift_analysis._create_session", return_value=session),
        patch(
            "app.services.drift_analysis._extract_and_save_code_changes",
            side_effect=RuntimeError("something broke"),
        ),
        patch("app.services.drift_analysis.asyncio.run"),
        patch("app.services.drift_analysis.update_github_check_run", new_callable=MagicMock),
        patch("app.services.drift_analysis.create_notification") as mock_notif,
    ):
        with pytest.raises(RuntimeError):
            run_drift_analysis(drift_event_id)

    mock_notif.assert_not_called()


# Test wildcard pattern matching (e.g. *.cfg and directory prefix patterns)
def test_extract_and_save_code_changes_wildcard_pattern():
    drift_event = _make_drift_event(file_ignore_patterns=["*.cfg", "config/*"])
    session = MagicMock()

    git_diff_output = "M\tsetup.cfg\nM\tconfig/settings.py\nM\tsrc/service.py\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_diff_output

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.drift_analysis.get_local_repo_path") as mock_path,
    ):
        mock_path.return_value = MagicMock(spec=Path, exists=MagicMock(return_value=True))

        _extract_and_save_code_changes(session, drift_event)

    added_changes = [c.args[0] for c in session.add.call_args_list]
    is_ignored_flags = {c.file_path: c.is_ignored for c in added_changes}

    assert is_ignored_flags["setup.cfg"] is True
    assert is_ignored_flags["config/settings.py"] is True
    assert is_ignored_flags["src/service.py"] is False
