import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.github_webhook import handle_github_event
from app.models.installation import Installation
from app.models.repository import Repository


# =========== handle_installation Tests ===========


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

    await handle_github_event(mock_db_session, "installation", payload)
    assert mock_db_session.execute.call_count >= 2


# Test that GH app deletion removes installation and cascades
@pytest.mark.asyncio
async def test_handle_installation_deleted(mock_db_session):
    payload = {"action": "deleted", "installation": {"id": 123}}

    await handle_github_event(mock_db_session, "installation", payload)

    mock_db_session.query.assert_called_with(Installation)
    mock_db_session.query.return_value.filter.assert_called()
    mock_db_session.query.return_value.filter.return_value.delete.assert_called_once()


# Test that GH app suspension marks all linked repos as suspended
@pytest.mark.asyncio
async def test_handle_installation_suspend(mock_db_session):
    payload = {"action": "suspend", "installation": {"id": 123}}

    await handle_github_event(mock_db_session, "installation", payload)

    # Should update all linked repos for that installation to is_suspended=True
    mock_db_session.query.assert_called_with(Repository)
    mock_db_session.query.return_value.filter.return_value.update.assert_called_once_with(
        {"is_suspended": True}
    )


# Test that GH app unsuspension marks all linked repos as active again
@pytest.mark.asyncio
async def test_handle_installation_unsuspend(mock_db_session):
    payload = {"action": "unsuspend", "installation": {"id": 123}}

    await handle_github_event(mock_db_session, "installation", payload)

    # Should update all linked repos for that installation to is_suspended=False
    mock_db_session.query.assert_called_with(Repository)
    mock_db_session.query.return_value.filter.return_value.update.assert_called_once_with(
        {"is_suspended": False}
    )


# =========== Notification Tests ===========


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
            "app.services.github_webhook.repository_handlers.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.github_webhook.repository_handlers.clone_repository",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.github_webhook.installation_handlers.create_notification"
        ) as mock_notif,
    ):
        await handle_github_event(mock_db, "installation", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "test-org" in content
    assert "connected" in content
    assert "2 repositories" in content


# Test that the notification uses "repository" (singular) when only 1 repo is linked
@pytest.mark.asyncio
async def test_notification_on_installation_created_singular_repo():
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
        "repositories": [{"full_name": "test-org/only-repo"}],  # just 1 repo
    }

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    with (
        patch(
            "app.services.github_webhook.repository_handlers.get_installation_access_token",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.github_webhook.repository_handlers.clone_repository",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.github_webhook.installation_handlers.create_notification"
        ) as mock_notif,
    ):
        await handle_github_event(mock_db, "installation", payload)

    mock_notif.assert_called_once()
    _, _, content = mock_notif.call_args[0]
    assert "1 repository" in content
    assert "repositories" not in content


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

    with patch(
        "app.services.github_webhook.installation_handlers.create_notification"
    ) as mock_notif:
        await handle_github_event(mock_db, "installation", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "test-org" in content
    assert "disconnected" in content
