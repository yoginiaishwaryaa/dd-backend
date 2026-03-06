import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.github_api import create_github_check_run, update_github_check_run
from app.models.drift import DriftEvent
from app.services.github_webhook_service import handle_github_event


# Test that check runs are created successfully in GH
@pytest.mark.asyncio
async def test_create_check_run_success():
    mock_db = MagicMock()
    drift_event_id = "uuid-123"
    repo_full_name = "owner/repo"
    head_sha = "sha-123"
    installation_id = 12345

    with patch(
        "app.services.github_api.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        # Mock successful GH response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 987654321}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_github_check_run(
                mock_db, drift_event_id, repo_full_name, head_sha, installation_id
            )

            assert result == 987654321
            mock_client.post.assert_called_once()

            # Verify check run ID is saved to DB in the Drift Event
            mock_db.query.assert_called_with(DriftEvent)
            mock_db.commit.assert_called_once()

            # Verify the GH API call has correct params
            args, kwargs = mock_client.post.call_args
            assert args[0] == f"https://api.github.com/repos/{repo_full_name}/check-runs"
            payload = kwargs["json"]
            assert payload["name"] == "Delta Docs"
            assert payload["head_sha"] == head_sha
            assert payload["status"] == "queued"


# Test that API failures for create check run are handled gracefully
@pytest.mark.asyncio
async def test_create_check_run_api_failure():
    mock_db = MagicMock()
    drift_event_id = "uuid-123"
    repo_full_name = "owner/repo"
    head_sha = "sha-123"
    installation_id = 12345

    with patch(
        "app.services.github_api.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        # Mock GH API error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "GitHub Server Error"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_github_check_run(
                mock_db, drift_event_id, repo_full_name, head_sha, installation_id
            )

            # Should return None and not commit anything
            assert result is None
            mock_db.commit.assert_not_called()


# Test that PR events trigger check run creation
@pytest.mark.asyncio
async def test_handle_pr_triggers_check_run():
    mock_db = MagicMock()
    payload = {
        "action": "opened",
        "number": 123,
        "installation": {"id": 555},
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "base": {"sha": "base_sha", "ref": "main"},
            "head": {"sha": "head_sha", "ref": "feature-branch"},
        },
    }

    # Mock the linked repo lookup
    mock_repo = MagicMock()
    mock_repo.id = "uuid-repo-1"
    mock_repo.target_branch = "main"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

    with (
        patch(
            "app.services.github_webhook_service.create_github_check_run", new_callable=AsyncMock
        ) as mock_create_check,
        patch(
            "app.services.github_webhook_service.get_installation_access_token",
            new_callable=AsyncMock,
        ) as mock_get_token,
        patch("app.services.github_webhook_service.pull_branches", new_callable=AsyncMock),
        patch("app.services.github_webhook_service.create_notification"),
    ):
        mock_create_check.return_value = 123456789
        mock_get_token.return_value = "test_token"

        await handle_github_event(mock_db, "pull_request", payload)

        # Verify a drift event was created in DB
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify check run is created with correct params
        mock_create_check.assert_called_once()
        args, _ = mock_create_check.call_args
        assert args[0] == mock_db
        assert args[2] == "owner/repo"
        assert args[3] == "head_sha"
        assert args[4] == 555


# Test that check run updates successfully with in_progress status
@pytest.mark.asyncio
async def test_update_check_run_in_progress_success():
    repo_full_name = "owner/repo"
    check_run_id = 987654321
    installation_id = 12345

    with patch(
        "app.services.github_api.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        # Mock successful GH response
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await update_github_check_run(
                repo_full_name=repo_full_name,
                check_run_id=check_run_id,
                installation_id=installation_id,
                status="in_progress",
                title="Analyzing PR",
                summary="Drift analysis is in progress...",
            )

            assert result is True
            mock_client.patch.assert_called_once()

            # Verify the GH API call has correct params
            args, kwargs = mock_client.patch.call_args
            assert (
                args[0]
                == f"https://api.github.com/repos/{repo_full_name}/check-runs/{check_run_id}"
            )
            payload = kwargs["json"]
            assert payload["status"] == "in_progress"
            assert payload["output"]["title"] == "Analyzing PR"
            assert payload["output"]["summary"] == "Drift analysis is in progress..."
            assert "conclusion" not in payload
            assert "completed_at" not in payload


# Test that check run updates successfully with completed status
@pytest.mark.asyncio
async def test_update_check_run_completed_success():
    repo_full_name = "owner/repo"
    check_run_id = 987654321
    installation_id = 12345

    with patch(
        "app.services.github_api.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        # Mock successful GH response
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await update_github_check_run(
                repo_full_name=repo_full_name,
                check_run_id=check_run_id,
                installation_id=installation_id,
                status="completed",
                conclusion="success",
                title="Analysis Complete",
                summary="No drift detected!",
            )

            assert result is True
            mock_client.patch.assert_called_once()

            # Verify the GH API call has correct params
            args, kwargs = mock_client.patch.call_args
            assert (
                args[0]
                == f"https://api.github.com/repos/{repo_full_name}/check-runs/{check_run_id}"
            )
            payload = kwargs["json"]
            assert payload["status"] == "completed"
            assert payload["conclusion"] == "success"
            assert payload["output"]["title"] == "Analysis Complete"
            assert payload["output"]["summary"] == "No drift detected!"
            assert "completed_at" in payload


# Test that check run updates with failure conclusion
@pytest.mark.asyncio
async def test_update_check_run_completed_failure():
    repo_full_name = "owner/repo"
    check_run_id = 987654321
    installation_id = 12345

    with patch(
        "app.services.github_api.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        # Mock successful GH response
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await update_github_check_run(
                repo_full_name=repo_full_name,
                check_run_id=check_run_id,
                installation_id=installation_id,
                status="completed",
                conclusion="failure",
                title="Drift Detected",
                summary="Documentation is out of sync with code changes.",
            )

            assert result is True
            mock_client.patch.assert_called_once()

            # Verify the GH API call has correct params
            args, kwargs = mock_client.patch.call_args
            payload = kwargs["json"]
            assert payload["status"] == "completed"
            assert payload["conclusion"] == "failure"
            assert payload["output"]["title"] == "Drift Detected"


# Test that API failures are handled gracefully for update check run
@pytest.mark.asyncio
async def test_update_check_run_api_failure():
    repo_full_name = "owner/repo"
    check_run_id = 987654321
    installation_id = 12345

    with patch(
        "app.services.github_api.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        # Mock GH API error
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Check run not found"

        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await update_github_check_run(
                repo_full_name=repo_full_name,
                check_run_id=check_run_id,
                installation_id=installation_id,
                status="in_progress",
            )

            # Should return False on failure
            assert result is False
