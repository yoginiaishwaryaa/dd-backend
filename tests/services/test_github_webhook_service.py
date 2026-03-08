import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from app.services import github_webhook_service
from app.models.installation import Installation
from app.models.repository import Repository
from app.models.drift import DriftEvent


# Test fixture for mocking DB session
@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session


# Test that GH app installation creates installation and repo records
@pytest.mark.asyncio
async def test_handle_installation_created(mock_db_session):
    payload = {
        "action": "created",
        "installation": {
            "id": 123,
            "account": {
                "login": "test-org",
                "type": "Organization",
                "avatar_url": "http://avatar.url",
            },
        },
        "sender": {"id": 456},
        "repositories": [{"full_name": "test-org/repo1"}, {"full_name": "test-org/repo2"}],
    }

    await github_webhook_service.handle_github_event(mock_db_session, "installation", payload)
    assert mock_db_session.execute.call_count >= 2


# Test that GH app deletion removes installation and cascades
@pytest.mark.asyncio
async def test_handle_installation_deleted(mock_db_session):
    payload = {"action": "deleted", "installation": {"id": 123}}

    await github_webhook_service.handle_github_event(mock_db_session, "installation", payload)

    mock_db_session.query.assert_called_with(Installation)
    mock_db_session.query.return_value.filter.assert_called()
    mock_db_session.query.return_value.filter.return_value.delete.assert_called_once()


# Test that GH app suspension marks all linked repos as suspended
@pytest.mark.asyncio
async def test_handle_installation_suspend(mock_db_session):
    payload = {"action": "suspend", "installation": {"id": 123}}

    await github_webhook_service.handle_github_event(mock_db_session, "installation", payload)

    # Should update all linked repos for that installation to is_suspended=True
    mock_db_session.query.assert_called_with(Repository)
    mock_db_session.query.return_value.filter.return_value.update.assert_called_once_with(
        {"is_suspended": True}
    )


# Test that GH app unsuspension marks all linked repos as active again
@pytest.mark.asyncio
async def test_handle_installation_unsuspend(mock_db_session):
    payload = {"action": "unsuspend", "installation": {"id": 123}}

    await github_webhook_service.handle_github_event(mock_db_session, "installation", payload)

    # Should update all linked repos for that installation to is_suspended=False
    mock_db_session.query.assert_called_with(Repository)
    mock_db_session.query.return_value.filter.return_value.update.assert_called_once_with(
        {"is_suspended": False}
    )


# Test adding repos to an installation
@pytest.mark.asyncio
async def test_handle_repos_added(mock_db_session):
    payload = {
        "action": "added",
        "installation": {"id": 123, "account": {"avatar_url": "http://avatar.url"}},
        "repositories_added": [{"full_name": "test-org/new-repo"}],
    }

    await github_webhook_service.handle_github_event(
        mock_db_session, "installation_repositories", payload
    )

    mock_db_session.execute.assert_called_once()


# Test removing repos from an installation
@pytest.mark.asyncio
async def test_handle_repos_removed(mock_db_session):
    payload = {
        "action": "removed",
        "installation": {"id": 123},
        "repositories_removed": [{"full_name": "test-org/old-repo"}],
    }

    await github_webhook_service.handle_github_event(
        mock_db_session, "installation_repositories", payload
    )

    mock_db_session.query.assert_called_with(Repository)
    mock_db_session.query.return_value.filter.return_value.delete.assert_called_once()


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
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch(
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ) as mock_get_token,
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch("app.services.github_webhook_service.create_notification"),
    ):
        mock_get_token.return_value = "test_token"
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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

    await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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

    await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

    # Should not create a drift event if the repo doesn't exist
    mock_db.add.assert_not_called()


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
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch(
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ) as mock_get_token,
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch("app.services.github_webhook_service.task_queue") as mock_task_queue,
        patch("app.services.github_webhook_service.run_drift_analysis") as mock_run_drift_analysis,
    ):
        mock_get_token.return_value = "test_token"

        # Setup mock_db.add to capture the drift event
        drift_id = uuid.uuid4()

        def capture_drift_event(obj):
            if isinstance(obj, DriftEvent):
                obj.id = drift_id

        mock_db.add.side_effect = capture_drift_event

        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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

    with patch("app.services.github_webhook_service.task_queue") as mock_task_queue:
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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

    with patch("app.services.github_webhook_service.task_queue") as mock_task_queue:
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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

    with patch("app.services.github_webhook_service.task_queue") as mock_task_queue:
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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
        patch("app.services.github_webhook_service.task_queue") as mock_task_queue,
        patch(
            "app.services.github_webhook_service.create_skipped_check_run", new_callable=AsyncMock
        ),
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

        # Verify task was not enqueued for deactivated repo
        mock_task_queue.enqueue.assert_not_called()


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
        "app.services.github_webhook_service.create_skipped_check_run", new_callable=AsyncMock
    ) as mock_skipped_check_run:
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

        # Verify a skipped check run was created on GitHub so the PR shows correct status
        mock_skipped_check_run.assert_called_once_with(
            "owner/repo",
            "head456",
            100,
            "Drift analysis is disabled for this repository. Enable it in Delta to resume tracking.",
        )


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
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch(
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "PR #7" in content
    assert "owner/repo" in content
    assert "queued for drift analysis" in content


# Test notification is sent when repos are linked to an installation
@pytest.mark.asyncio
async def test_notification_on_repos_added():
    user_id = uuid.uuid4()
    mock_db = MagicMock()
    payload = {
        "action": "added",
        "installation": {"id": 123, "account": {"avatar_url": "http://avatar.url"}},
        "repositories_added": [{"full_name": "test-org/new-repo"}],
    }

    mock_installation = MagicMock()
    mock_installation.user_id = user_id
    mock_db.query.return_value.filter.return_value.first.return_value = mock_installation

    with (
        patch(
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.clone_repository", new_callable=AsyncMock),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(
            mock_db, "installation_repositories", payload
        )

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "test-org/new-repo" in content
    assert "linked" in content


# Test notification is sent when repos are unlinked from an installation
@pytest.mark.asyncio
async def test_notification_on_repos_removed():
    user_id = uuid.uuid4()
    mock_db = MagicMock()
    payload = {
        "action": "removed",
        "installation": {"id": 123},
        "repositories_removed": [{"full_name": "test-org/old-repo"}],
    }

    mock_installation = MagicMock()
    mock_installation.user_id = user_id
    mock_db.query.return_value.filter.return_value.first.return_value = mock_installation

    with (
        patch("app.services.github_webhook_service.remove_cloned_repository"),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(
            mock_db, "installation_repositories", payload
        )

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "test-org/old-repo" in content
    assert "unlinked" in content


# Test notification is sent when GitHub account is connected
@pytest.mark.asyncio
async def test_notification_on_installation_created():
    user_id = uuid.uuid4()
    mock_db = MagicMock()
    payload = {
        "action": "created",
        "installation": {
            "id": 123,
            "account": {
                "login": "test-org",
                "type": "Organization",
                "avatar_url": "http://avatar.url",
            },
        },
        "sender": {"id": 456},
        "repositories": [{"full_name": "test-org/repo1"}, {"full_name": "test-org/repo2"}],
    }

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    with (
        patch(
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.clone_repository", new_callable=AsyncMock),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(mock_db, "installation", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "test-org" in content
    assert "connected" in content
    assert "2 repositories" in content


# Test notification is sent when GitHub account is disconnected
@pytest.mark.asyncio
async def test_notification_on_installation_deleted():
    user_id = uuid.uuid4()
    mock_db = MagicMock()
    payload = {
        "action": "deleted",
        "installation": {"id": 123, "account": {"login": "test-org"}},
    }

    mock_installation = MagicMock()
    mock_installation.user_id = user_id
    mock_db.query.return_value.filter.return_value.first.return_value = mock_installation

    with patch("app.services.github_webhook_service.create_notification") as mock_notif:
        await github_webhook_service.handle_github_event(mock_db, "installation", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "test-org" in content
    assert "disconnected" in content


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
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch(
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ) as mock_get_token,
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch("app.services.github_webhook_service.task_queue") as mock_task_queue,
        patch("app.services.github_webhook_service.run_drift_analysis"),
    ):
        mock_get_token.return_value = "test_token"

        # Setup mock_db to simulate drift event creation
        mock_drift_event = MagicMock()
        drift_id = uuid.uuid4()
        mock_drift_event.id = drift_id

        def add_side_effect(obj):
            if isinstance(obj, DriftEvent):
                obj.id = drift_id

        mock_db.add.side_effect = add_side_effect

        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

        # Verify drift event ID is passed as string
        args, _ = mock_task_queue.enqueue.call_args
        assert args[1] == str(drift_id)
        assert isinstance(args[1], str)


# Helper function to create a check_suite rerequested payload
def _make_check_suite_payload(head_sha="sha999", repo_full_name="owner/repo", installation_id=100):
    return {
        "action": "rerequested",
        "check_suite": {"head_sha": head_sha},
        "repository": {"full_name": repo_full_name},
        "installation": {"id": installation_id},
    }


# Helper function that returns a mock db whose DriftEvent query chain returns drift_event
def _make_check_suite_db(drift_event):
    mock_db = MagicMock()
    (
        mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value
    ) = drift_event
    return mock_db


# Test that check_suite rerequested with valid payload resets drift event and re-enqueues analysis
@pytest.mark.asyncio
async def test_check_suite_rerequested_resets_and_requeues():
    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    drift_event.head_sha = "sha999"
    mock_db = _make_check_suite_db(drift_event)
    payload = _make_check_suite_payload()

    with (
        patch(
            "app.services.github_webhook_service.create_github_check_run",
            new_callable=AsyncMock,
        ) as mock_create_check_run,
        patch("app.services.github_webhook_service.task_queue") as mock_task_queue,
        patch("app.services.github_webhook_service.run_drift_analysis") as mock_run,
    ):
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    mock_create_check_run.assert_called_once_with(
        mock_db, str(drift_event.id), "owner/repo", drift_event.head_sha, 100
    )
    mock_task_queue.enqueue.assert_called_once_with(mock_run, str(drift_event.id))


# Test that missing head_sha in payload causes early return without touching DB
@pytest.mark.asyncio
async def test_check_suite_rerequested_missing_head_sha():
    mock_db = MagicMock()
    payload = {
        "check_suite": {},  # no head_sha
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 100},
    }

    with patch("app.services.github_webhook_service.task_queue") as mock_task_queue:
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    mock_db.flush.assert_not_called()
    mock_task_queue.enqueue.assert_not_called()


# Test that a missing installation_id causes early return
@pytest.mark.asyncio
async def test_check_suite_rerequested_missing_installation_id():
    mock_db = MagicMock()
    payload = {
        "check_suite": {"head_sha": "sha999"},
        "repository": {"full_name": "owner/repo"},
        "installation": {},  # no id
    }

    with patch("app.services.github_webhook_service.task_queue") as mock_task_queue:
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    mock_db.flush.assert_not_called()
    mock_task_queue.enqueue.assert_not_called()


# Test that when no drift event is found for the head_sha, nothing is re-enqueued
@pytest.mark.asyncio
async def test_check_suite_rerequested_no_drift_event_found():
    mock_db = _make_check_suite_db(None)  # that is when first() returns None
    payload = _make_check_suite_payload()

    with patch("app.services.github_webhook_service.task_queue") as mock_task_queue:
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    mock_db.flush.assert_not_called()
    mock_task_queue.enqueue.assert_not_called()


# Test that stale DriftFindings and CodeChanges are deleted before re-queuing
@pytest.mark.asyncio
async def test_check_suite_rerequested_clears_stale_findings_and_changes():
    from app.models.drift import DriftFinding, CodeChange

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    mock_db = _make_check_suite_db(drift_event)
    payload = _make_check_suite_payload()

    deleted_models = []

    def track_deletes(model):
        m = MagicMock()
        m.filter.return_value.delete = MagicMock(
            side_effect=lambda **kw: deleted_models.append(model)
        )
        m.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
            drift_event
        )
        return m

    mock_db.query.side_effect = track_deletes

    with (
        patch(
            "app.services.github_webhook_service.create_github_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.task_queue"),
    ):
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    assert DriftFinding in deleted_models
    assert CodeChange in deleted_models


# Test that all drift event fields are reset to clean queued state
@pytest.mark.asyncio
async def test_check_suite_rerequested_resets_drift_event_fields():
    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    mock_db = _make_check_suite_db(drift_event)
    payload = _make_check_suite_payload()

    with (
        patch(
            "app.services.github_webhook_service.create_github_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.task_queue"),
    ):
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    assert drift_event.processing_phase == "queued"
    assert drift_event.drift_result == "pending"
    assert drift_event.overall_drift_score is None
    assert drift_event.summary is None
    assert drift_event.agent_logs == {}
    assert drift_event.error_message is None
    assert drift_event.started_at is None
    assert drift_event.completed_at is None
    assert drift_event.check_run_id is None
    mock_db.flush.assert_called_once()


# Test that unrelated check_suite actions are ignored
@pytest.mark.asyncio
async def test_check_suite_non_rerequested_action_ignored():
    mock_db = MagicMock()
    payload = {
        "action": "completed",
        "check_suite": {"head_sha": "sha999"},
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 100},
    }

    with patch("app.services.github_webhook_service.task_queue") as mock_task_queue:
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    mock_task_queue.enqueue.assert_not_called()


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
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch(
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ) as mock_check_run,
        patch("app.services.github_webhook_service.task_queue") as mock_queue,
        patch("app.services.github_webhook_service.run_drift_analysis") as mock_run,
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch(
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch("app.services.github_webhook_service.task_queue"),
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch(
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch("app.services.github_webhook_service.task_queue") as mock_queue,
        patch("app.services.github_webhook_service.run_drift_analysis"),
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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
            "app.services.github_webhook_service.create_skipped_check_run", new_callable=AsyncMock
        ) as mock_skip,
        patch("app.services.github_webhook_service.task_queue") as mock_queue,
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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

    with patch("app.services.github_webhook_service.task_queue") as mock_queue:
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

    mock_queue.enqueue.assert_not_called()


# Test that synchronize for an unknown repo is handled
@pytest.mark.asyncio
async def test_pr_synchronize_repo_not_found():
    mock_db = _make_sync_db(repo=None)
    payload = _make_sync_payload()

    with patch("app.services.github_webhook_service.task_queue") as mock_queue:
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch(
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ) as mock_check_run,
        patch("app.services.github_webhook_service.task_queue"),
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

    args, _ = mock_check_run.call_args
    assert args[3] == "latest_sha"


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
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch(
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch("app.services.github_webhook_service.task_queue"),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

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
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch(
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ),
        patch("app.services.github_webhook_service.task_queue"),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(mock_db, "pull_request", payload)

    mock_notif.assert_not_called()


# Test notification is sent when drift analysis is re-queued via check suite re-request
@pytest.mark.asyncio
async def test_notification_on_check_suite_rerequested():
    user_id = uuid.uuid4()

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    drift_event.pr_number = 22
    drift_event.head_sha = "sha999"

    mock_installation = MagicMock()
    mock_installation.user_id = user_id

    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        if model == DriftEvent:
            m.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
                drift_event
            )
        elif model == Installation:
            m.filter.return_value.first.return_value = mock_installation
        else:
            m.filter.return_value.delete.return_value = None
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_side_effect
    payload = _make_check_suite_payload(
        head_sha="sha999", repo_full_name="owner/repo", installation_id=100
    )

    with (
        patch(
            "app.services.github_webhook_service.create_github_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.task_queue"),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "PR #22" in content
    assert "owner/repo" in content
    assert "re-queued" in content


# Test no notification on check suite rerequested when no user_id
@pytest.mark.asyncio
async def test_no_notification_on_check_suite_rerequested_when_no_user_id():
    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    drift_event.pr_number = 22
    drift_event.head_sha = "sha999"

    mock_installation = MagicMock()
    mock_installation.user_id = None

    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        if model == DriftEvent:
            m.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
                drift_event
            )
        elif model == Installation:
            m.filter.return_value.first.return_value = mock_installation
        else:
            m.filter.return_value.delete.return_value = None
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_side_effect
    payload = _make_check_suite_payload()

    with (
        patch(
            "app.services.github_webhook_service.create_github_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook_service.task_queue"),
        patch("app.services.github_webhook_service.create_notification") as mock_notif,
    ):
        await github_webhook_service.handle_github_event(mock_db, "check_suite", payload)

    mock_notif.assert_not_called()
