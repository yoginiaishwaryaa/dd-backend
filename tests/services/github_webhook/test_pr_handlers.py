import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.github_webhook import handle_github_event
from app.models.installation import Installation
from app.models.repository import Repository
from app.models.drift import DriftEvent


# =========== Helper Functions ===========


# Helper function to create a pull_request synchronize payload
def _make_sync_payload(
    pr_number=42,
    base_sha="newbase",
    head_sha="newhead",
    base_ref="main",
    head_ref="feature",
    is_fork=False,
    repo_full_name="owner/repo",
    installation_id=100,
):
    return {
        "action": "synchronize",
        "number": pr_number,
        "installation": {"id": installation_id},
        "repository": {"full_name": repo_full_name},
        "pull_request": {
            "base": {"sha": base_sha, "ref": base_ref},
            "head": {"sha": head_sha, "ref": head_ref, "repo": {"fork": is_fork}},
        },
    }


# Helper function that returns a mock db for pr_synchronize tests
def _make_sync_db(repo, drift_event=None):
    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        if model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == DriftEvent:
            m.filter.return_value.order_by.return_value.first.return_value = drift_event
        else:
            m.filter.return_value.delete.return_value = None
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_side_effect
    return mock_db


# =========== handle_pr_opened Tests ===========


# Test that PR opened creates a drift event
@pytest.mark.asyncio
async def test_handle_pr_opened_success():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 123,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "feature-branch"},
        },
    }

    # Mock the repo lookup
    mock_repo = MagicMock()
    mock_repo.id = "uuid-123"
    mock_repo.target_branch = "main"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.create_notification"),
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    # Verify drift event was created with correct data
    mock_db.query.assert_called()
    mock_db.add.assert_called_once()
    args, _ = mock_db.add.call_args
    event = args[0]
    assert isinstance(event, DriftEvent)
    assert event.repo_id == "uuid-123"
    assert event.pr_number == 123
    assert event.base_sha == "base123"
    assert event.head_sha == "head456"
    assert event.processing_phase == "queued"


# Test that non relevant PR actions (like closing, assigning, etc.) are ignored
@pytest.mark.asyncio
async def test_handle_pr_ignored_action():
    mock_db = MagicMock()
    payload = {"action": "closed"}

    await handle_github_event(mock_db, "pull_request", payload)

    # Shouldn't add any records
    mock_db.add.assert_not_called()


# Test that PRs for unknown repos are handled gracefully
@pytest.mark.asyncio
async def test_repo_not_found_for_pr():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "installation": {"id": 999},
        "repository": {"full_name": "unknown/repo"},
    }

    # Mock no repo found
    mock_db.query.return_value.filter.return_value.first.return_value = None

    await handle_github_event(mock_db, "pull_request", payload)

    # Should not create a drift event if the repo doesn't exist
    mock_db.add.assert_not_called()


# Test that a PR opened from Delta's own docs-fix branch creates a skipped check run
@pytest.mark.asyncio
async def test_pr_opened_for_docs_fix_branch_creates_skipped_check_run():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 200,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "docs/delta-fix/feature"},
        },
    }

    mock_repo = MagicMock()
    mock_repo.is_active = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_skipped_check_run",
            new_callable=AsyncMock,
        ) as mock_skip,
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue,
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    mock_skip.assert_called_once_with(
        "owner/repo",
        "head456",
        100,
        "This PR was auto-generated by Delta to resolve documentation drift. No analysis required.",
    )
    mock_db.add.assert_not_called()
    mock_queue.enqueue.assert_not_called()


# =========== RQ Integration Tests ===========


# Test that drift event ID is passed as string to the task
@pytest.mark.asyncio
async def test_drift_event_id_passed_as_string():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 123,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "feature-branch"},
        },
    }

    mock_repo = MagicMock()
    mock_repo.id = "uuid-123"
    mock_repo.target_branch = "main"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_task_queue,
        patch("app.services.github_webhook.pr_handlers.run_drift_analysis"),
    ):
        # Setup mock_db to simulate drift event creation
        mock_drift_event = MagicMock()
        drift_id = uuid.uuid4()
        mock_drift_event.id = drift_id

        def add_side_effect(obj):
            if isinstance(obj, DriftEvent):
                obj.id = drift_id

        mock_db.add.side_effect = add_side_effect

        await handle_github_event(mock_db, "pull_request", payload)

        # Verify drift event ID is passed as string
        args, _ = mock_task_queue.enqueue.call_args
        assert args[1] == str(drift_id)
        assert isinstance(args[1], str)


# Test that task is enqueued when PR is opened
@pytest.mark.asyncio
async def test_pr_opened_enqueues_task():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 123,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "feature-branch"},
        },
    }

    # Mock the repo lookup
    mock_repo = MagicMock()
    mock_repo.id = "uuid-123"
    mock_repo.target_branch = "main"

    # Mock the drift event that gets created
    mock_drift_event = MagicMock()
    mock_drift_event.id = "drift-event-uuid"

    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_task_queue,
        patch(
            "app.services.github_webhook.pr_handlers.run_drift_analysis"
        ) as mock_run_drift_analysis,
    ):
        # Setup mock_db.add to capture the drift event
        drift_id = uuid.uuid4()

        def capture_drift_event(obj):
            if isinstance(obj, DriftEvent):
                obj.id = drift_id

        mock_db.add.side_effect = capture_drift_event

        await handle_github_event(mock_db, "pull_request", payload)

        # Verify task was enqueued with the drift event ID
        mock_task_queue.enqueue.assert_called_once()
        args, _ = mock_task_queue.enqueue.call_args
        assert args[0] == mock_run_drift_analysis

        # The drift event ID is passed as a string
        assert args[1] == str(drift_id)
        assert isinstance(args[1], str)


# Test that task is not enqueued for unsupported PR actions
@pytest.mark.asyncio
async def test_pr_reopened_not_enqueued():
    mock_db = MagicMock()
    payload = {
        "action": "reopened",
        "number": 789,
        "installation": {"id": 300},
        "repository": {"full_name": "owner/repo3"},
        "pull_request": {
            "base": {"sha": "base345", "ref": "main"},
            "head": {"sha": "head678", "ref": "test-branch"},
        },
    }

    with patch("app.services.github_webhook.pr_handlers.task_queue") as mock_task_queue:
        await handle_github_event(mock_db, "pull_request", payload)

        # Verify that the task was not enqueued in this situation
        mock_task_queue.enqueue.assert_not_called()


# Test that task is not enqueued when repo is not found
@pytest.mark.asyncio
async def test_pr_no_task_when_repo_not_found():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "installation": {"id": 999},
        "repository": {"full_name": "unknown/repo"},
    }

    # Mock no repo found
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("app.services.github_webhook.pr_handlers.task_queue") as mock_task_queue:
        await handle_github_event(mock_db, "pull_request", payload)

        # Verify task was not enqueued
        mock_task_queue.enqueue.assert_not_called()


# Test that task is not enqueued when repo is suspended
@pytest.mark.asyncio
async def test_pr_no_task_when_repo_suspended():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 101,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "feature-branch"},
        },
    }

    mock_repo = MagicMock()
    mock_repo.is_suspended = True
    mock_repo.is_active = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with patch("app.services.github_webhook.pr_handlers.task_queue") as mock_task_queue:
        await handle_github_event(mock_db, "pull_request", payload)

        # Verify task was not enqueued for suspended repo
        mock_task_queue.enqueue.assert_not_called()


# Test that task is not enqueued when repo is deactivated
@pytest.mark.asyncio
async def test_pr_no_task_when_repo_deactivated():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 102,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "feature-branch"},
        },
    }

    mock_repo = MagicMock()
    mock_repo.is_suspended = False
    mock_repo.is_active = False
    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with (
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_task_queue,
        patch(
            "app.services.github_webhook.pr_handlers.create_skipped_check_run",
            new_callable=AsyncMock,
        ),
    ):
        await handle_github_event(mock_db, "pull_request", payload)

        # Verify task was not enqueued for deactivated repo
        mock_task_queue.enqueue.assert_not_called()


# =========== GH Check Run Integration Tests ===========


# Test that a skipped check run is created on GitHub when repo is deactivated
@pytest.mark.asyncio
async def test_pr_skipped_check_run_when_repo_deactivated():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 103,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "feature-branch"},
        },
    }

    mock_repo = MagicMock()
    mock_repo.is_suspended = False
    mock_repo.is_active = False
    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with patch(
        "app.services.github_webhook.pr_handlers.create_skipped_check_run", new_callable=AsyncMock
    ) as mock_skipped_check_run:
        await handle_github_event(mock_db, "pull_request", payload)

        # Verify a skipped check run was created on GitHub so the PR shows correct status
        mock_skipped_check_run.assert_called_once_with(
            "owner/repo",
            "head456",
            100,
            "Drift analysis is disabled for this repository. Enable it in Delta to resume tracking.",
        )


# =========== handle_pr_synchronize Tests ===========


# Test that an existing drift event is reset and re-enqueued with updated SHAs
@pytest.mark.asyncio
async def test_pr_synchronize_resets_existing_event():
    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()

    mock_db = _make_sync_db(mock_repo, drift_event)
    payload = _make_sync_payload()

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ) as mock_check_run,
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue,
        patch("app.services.github_webhook.pr_handlers.run_drift_analysis") as mock_run,
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    # SHAs updated
    assert drift_event.base_sha == "newbase"
    assert drift_event.head_sha == "newhead"

    # Reset to queued state
    assert drift_event.processing_phase == "queued"
    assert drift_event.drift_result == "pending"
    assert drift_event.check_run_id is None
    mock_db.flush.assert_called_once()

    # Check run called and task enqueued
    mock_check_run.assert_called_once()
    mock_queue.enqueue.assert_called_once_with(mock_run, str(drift_event.id))


# Test that stale findings and code changes are deleted on synchronize
@pytest.mark.asyncio
async def test_pr_synchronize_clears_stale_data():
    from app.models.drift import DriftFinding, CodeChange

    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()

    deleted_models = []

    def query_side_effect(model):
        m = MagicMock()
        if model == Repository:
            m.filter.return_value.first.return_value = mock_repo
        elif model == DriftEvent:
            m.filter.return_value.order_by.return_value.first.return_value = drift_event
        else:
            # DriftFinding / CodeChange deletes
            m.filter.return_value.delete = MagicMock(
                side_effect=lambda **kw: deleted_models.append(model)
            )
        return m

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect
    payload = _make_sync_payload()

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.task_queue"),
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    assert DriftFinding in deleted_models
    assert CodeChange in deleted_models


# Test that a fresh drift event is created when no existing one is found for pr_synchronize
@pytest.mark.asyncio
async def test_pr_synchronize_creates_new_event_if_none_exists():
    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    mock_db = _make_sync_db(mock_repo, drift_event=None)  # no existing event
    payload = _make_sync_payload()

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue,
        patch("app.services.github_webhook.pr_handlers.run_drift_analysis"),
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    # A new DriftEvent should be added
    mock_db.add.assert_called_once()
    args, _ = mock_db.add.call_args
    new_event = args[0]

    assert isinstance(new_event, DriftEvent)
    assert new_event.pr_number == 42
    assert new_event.base_sha == "newbase"
    assert new_event.head_sha == "newhead"
    mock_queue.enqueue.assert_called_once()


# Test that synchronize for a deactivated repo creates a skipped check run
@pytest.mark.asyncio
async def test_pr_synchronize_skipped_when_repo_deactivated():
    mock_repo = MagicMock()
    mock_repo.is_active = False
    mock_db = _make_sync_db(mock_repo)
    payload = _make_sync_payload()

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_skipped_check_run",
            new_callable=AsyncMock,
        ) as mock_skip,
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue,
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    mock_skip.assert_called_once_with(
        "owner/repo",
        "newhead",
        100,
        "Drift analysis is disabled for this repository. Enable it in Delta to resume tracking.",
    )
    mock_queue.enqueue.assert_not_called()


# Test that synchronize with missing fields causes early return
@pytest.mark.asyncio
async def test_pr_synchronize_missing_fields():
    mock_db = MagicMock()
    payload = {
        "action": "synchronize",
        "installation": {"id": 100},
        "repository": {},  # missing full_name
        "pull_request": {
            "base": {"sha": "b", "ref": "main"},
            "head": {"sha": "h", "ref": "feat"},
        },
    }

    with patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue:
        await handle_github_event(mock_db, "pull_request", payload)

    mock_queue.enqueue.assert_not_called()


# Test that synchronize for an unknown repo is handled
@pytest.mark.asyncio
async def test_pr_synchronize_repo_not_found():
    mock_db = _make_sync_db(repo=None)
    payload = _make_sync_payload()

    with patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue:
        await handle_github_event(mock_db, "pull_request", payload)

    mock_queue.enqueue.assert_not_called()


# Test that the check run is created with the new head SHA
@pytest.mark.asyncio
async def test_pr_synchronize_check_run_uses_new_head_sha():
    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()

    mock_db = _make_sync_db(mock_repo, drift_event)
    payload = _make_sync_payload(head_sha="latest_sha")

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ) as mock_check_run,
        patch("app.services.github_webhook.pr_handlers.task_queue"),
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    args, _ = mock_check_run.call_args
    assert args[3] == "latest_sha"


# Test that a merge commit mentioning the docs PR number triggers fix_pr_merged
@pytest.mark.asyncio
async def test_pr_synchronize_docs_fix_merge_detected():
    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    existing_event = MagicMock()
    existing_event.id = uuid.uuid4()
    existing_event.docs_pr_number = 55
    existing_event.processing_phase = "fix_pr_raised"

    mock_db = _make_sync_db(mock_repo, existing_event)
    payload = _make_sync_payload(head_sha="merge_sha")

    commit_data = {
        "commit": {"message": "Merge pull request #55 from owner/docs-fix"},
        "parents": [{"sha": "p1"}, {"sha": "p2"}],  # two parents = merge commit
    }

    with (
        patch(
            "app.services.github_webhook.pr_handlers.get_commit", new_callable=AsyncMock
        ) as mock_get_commit,
        patch(
            "app.services.github_webhook.pr_handlers.create_success_check_run",
            new_callable=AsyncMock,
        ) as mock_success,
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue,
    ):
        mock_get_commit.return_value = commit_data
        await handle_github_event(mock_db, "pull_request", payload)

    assert existing_event.processing_phase == "fix_pr_merged"
    mock_success.assert_called_once()

    # Returns early with no re-queuing
    mock_queue.enqueue.assert_not_called()


# Test that a non-merge commit falls through to normal re-analysis
@pytest.mark.asyncio
async def test_pr_synchronize_docs_fix_not_a_merge_commit_falls_through():
    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    existing_event = MagicMock()
    existing_event.id = uuid.uuid4()
    existing_event.docs_pr_number = 55
    existing_event.processing_phase = "fix_pr_raised"

    mock_db = _make_sync_db(mock_repo, existing_event)
    payload = _make_sync_payload(head_sha="normal_sha")

    # Regular commit with only one parent
    commit_data = {
        "commit": {"message": "fix: regular commit"},
        "parents": [{"sha": "p1"}],
    }

    with (
        patch(
            "app.services.github_webhook.pr_handlers.get_commit", new_callable=AsyncMock
        ) as mock_get_commit,
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ) as mock_check_run,
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue,
        patch("app.services.github_webhook.pr_handlers.run_drift_analysis"),
    ):
        mock_get_commit.return_value = commit_data
        await handle_github_event(mock_db, "pull_request", payload)

    # Re-queued for normal analysis
    assert existing_event.processing_phase == "queued"
    mock_check_run.assert_called_once()
    mock_queue.enqueue.assert_called_once()


# Test that a merge commit not mentioning the correct docs PR falls through
@pytest.mark.asyncio
async def test_pr_synchronize_docs_fix_merge_wrong_pr_number_falls_through():
    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    existing_event = MagicMock()
    existing_event.id = uuid.uuid4()
    existing_event.docs_pr_number = 55
    existing_event.processing_phase = "fix_pr_raised"

    mock_db = _make_sync_db(mock_repo, existing_event)
    payload = _make_sync_payload(head_sha="merge_sha2")

    # Merge commit but mentions a different PR number
    commit_data = {
        "commit": {"message": "Merge pull request #99 from owner/unrelated"},
        "parents": [{"sha": "p1"}, {"sha": "p2"}],
    }

    with (
        patch(
            "app.services.github_webhook.pr_handlers.get_commit", new_callable=AsyncMock
        ) as mock_get_commit,
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.task_queue") as mock_queue,
        patch("app.services.github_webhook.pr_handlers.run_drift_analysis"),
    ):
        mock_get_commit.return_value = commit_data
        await handle_github_event(mock_db, "pull_request", payload)

    # Re-queued for normal analysis
    assert existing_event.processing_phase == "queued"
    mock_queue.enqueue.assert_called_once()


# =========== Notification Tests ===========


# Test notification is sent when a PR is queued for drift analysis
@pytest.mark.asyncio
async def test_notification_on_pr_queued():
    user_id = uuid.uuid4()
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 7,
        "installation": {"id": 100},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base123", "ref": "main"},
            "head": {"sha": "head456", "ref": "feature-branch"},
        },
    }

    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.target_branch = "main"

    mock_installation = MagicMock()
    mock_installation.user_id = user_id

    # Return different objects depending on which model is queried
    def mock_query(model):
        m = MagicMock()
        if model == Repository:
            m.filter.return_value.first.return_value = mock_repo
        elif model == Installation:
            m.filter.return_value.first.return_value = mock_installation
        else:
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = mock_query

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.create_notification") as mock_notif,
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "PR #7" in content
    assert "owner/repo" in content
    assert "queued for drift analysis" in content


# Test notification is sent when new changes are pushed to an open PR
@pytest.mark.asyncio
async def test_notification_on_pr_synchronize():
    user_id = uuid.uuid4()

    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()

    mock_installation = MagicMock()
    mock_installation.user_id = user_id

    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        if model == Repository:
            m.filter.return_value.first.return_value = mock_repo
        elif model == DriftEvent:
            m.filter.return_value.order_by.return_value.first.return_value = drift_event
        elif model == Installation:
            m.filter.return_value.first.return_value = mock_installation
        else:
            m.filter.return_value.delete.return_value = None
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_side_effect
    payload = _make_sync_payload(pr_number=15, repo_full_name="owner/repo")

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.task_queue"),
        patch("app.services.github_webhook.pr_handlers.create_notification") as mock_notif,
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "PR #15" in content
    assert "owner/repo" in content
    assert "new commits" in content


# Test no notification on PR synchronize when no user_id
@pytest.mark.asyncio
async def test_no_notification_on_pr_synchronize_when_no_user_id():
    mock_repo = MagicMock()
    mock_repo.id = uuid.uuid4()
    mock_repo.is_active = True
    mock_repo.target_branch = "main"

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()

    mock_installation = MagicMock()
    mock_installation.user_id = None

    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        if model == Repository:
            m.filter.return_value.first.return_value = mock_repo
        elif model == DriftEvent:
            m.filter.return_value.order_by.return_value.first.return_value = drift_event
        elif model == Installation:
            m.filter.return_value.first.return_value = mock_installation
        else:
            m.filter.return_value.delete.return_value = None
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_side_effect
    payload = _make_sync_payload()

    with (
        patch(
            "app.services.github_webhook.pr_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.pr_handlers.task_queue"),
        patch("app.services.github_webhook.pr_handlers.create_notification") as mock_notif,
    ):
        await handle_github_event(mock_db, "pull_request", payload)

    mock_notif.assert_not_called()
