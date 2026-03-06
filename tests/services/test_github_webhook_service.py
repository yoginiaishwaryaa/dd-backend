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
