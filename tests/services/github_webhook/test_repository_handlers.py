import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.github_webhook import handle_github_event
from app.models.repository import Repository

# =========== handle_repos Tests ===========


# Test adding repos to an installation
@pytest.mark.asyncio
async def test_handle_repos_added(mock_db_session):
    payload = {
        "action": "added",
        "installation": {"id": 123, "account": {"avatar_url": "http://avatar.url"}},
        "repositories_added": [{"full_name": "test-org/new-repo"}],
    }

    await handle_github_event(mock_db_session, "installation_repositories", payload)

    mock_db_session.execute.assert_called_once()


# Test removing repos from an installation
@pytest.mark.asyncio
async def test_handle_repos_removed(mock_db_session):
    payload = {
        "action": "removed",
        "installation": {"id": 123},
        "repositories_removed": [{"full_name": "test-org/old-repo"}],
    }

    await handle_github_event(mock_db_session, "installation_repositories", payload)

    mock_db_session.query.assert_called_with(Repository)
    mock_db_session.query.return_value.filter.return_value.delete.assert_called_once()


# =========== Notification Tests ===========


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
            "app.services.github_webhook.repository_handlers.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.github_webhook.repository_handlers.clone_repository",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.repository_handlers.create_notification") as mock_notif,
    ):
        await handle_github_event(mock_db, "installation_repositories", payload)

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
        patch("app.services.github_webhook.repository_handlers.remove_cloned_repository"),
        patch("app.services.github_webhook.repository_handlers.create_notification") as mock_notif,
    ):
        await handle_github_event(mock_db, "installation_repositories", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "test-org/old-repo" in content
    assert "unlinked" in content
