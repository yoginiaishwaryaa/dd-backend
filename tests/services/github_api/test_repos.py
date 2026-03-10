import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.github_api import (
    get_commit,
    request_pr_review,
    create_docs_pull_request,
)
from app.services.github_api import get_repo_details


# =========== get_repo_details Tests ===========


# Test fetching repo details from GH API
@pytest.mark.asyncio
async def test_get_repo_details_success():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        with patch("app.services.github_api.repos.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            # Mock GH repo API response
            mock_repo_response = MagicMock()
            mock_repo_response.status_code = 200
            mock_repo_response.json.return_value = {
                "full_name": "repo-name",
                "description": "description",
                "language": "python",
                "stargazers_count": 10,
                "forks_count": 5,
            }

            mock_client_instance.get.return_value = mock_repo_response

            result = await get_repo_details(123, "owner", "repo")

            # Verify extraction of the right fields
            assert result["name"] == "repo-name"
            assert result["stargazers_count"] == 10
            mock_get_token.assert_awaited_once_with(123)


# =========== get_commit Tests ===========


# Test that get_commit returns commit data on success
@pytest.mark.asyncio
async def test_get_commit_success():
    commit_data = {"sha": "abc123", "commit": {"message": "feat: add endpoint"}, "parents": [{}]}

    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = commit_data

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_commit(100, "owner/repo", "abc123")

    assert result is not None
    assert result == commit_data
    assert result["sha"] == "abc123"


# Test that get_commit returns None when GH returns a non-200 status
@pytest.mark.asyncio
async def test_get_commit_not_found():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_commit(100, "owner/repo", "bad_sha")

    assert result is None


# Test that get_commit returns None when an exception occurs
@pytest.mark.asyncio
async def test_get_commit_exception():
    with patch(
        "app.services.github_api.repos.get_installation_access_token",
        new_callable=AsyncMock,
        side_effect=Exception("Network error"),
    ):
        result = await get_commit(100, "owner/repo", "sha123")

    assert result is None


# =========== request_pr_review Tests ===========


# Test that request_pr_review returns True on success
@pytest.mark.asyncio
async def test_request_pr_review_success():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 201

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await request_pr_review(100, "owner/repo", 42, "reviewer_login")

    assert result is True
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["reviewers"] == ["reviewer_login"]


# Test that request_pr_review returns False when GH returns an error
@pytest.mark.asyncio
async def test_request_pr_review_failure():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Reviewer not found"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await request_pr_review(100, "owner/repo", 42, "bad_reviewer")

    assert result is False


# Test that request_pr_review returns False when an exception occurs
@pytest.mark.asyncio
async def test_request_pr_review_exception():
    with patch(
        "app.services.github_api.repos.get_installation_access_token",
        new_callable=AsyncMock,
        side_effect=Exception("Network error"),
    ):
        result = await request_pr_review(100, "owner/repo", 42, "reviewer")

    assert result is False


# =========== create_docs_pull_request Tests ===========


# Test that create_docs_pull_request returns the new PR number on success
@pytest.mark.asyncio
async def test_create_docs_pull_request_success():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 88}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_docs_pull_request(
                installation_id=100,
                repo_full_name="owner/repo",
                head_branch="docs/delta-fix/feature",
                base_branch="feature",
                pr_number=42,
            )

    assert result == 88
    _, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    assert payload["head"] == "docs/delta-fix/feature"
    assert payload["base"] == "feature"
    assert "PR #42" in payload["title"]


# Test that body includes drift summary section when drift_summary is provided
@pytest.mark.asyncio
async def test_create_docs_pull_request_with_drift_summary():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 10}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_docs_pull_request(
                installation_id=100,
                repo_full_name="owner/repo",
                head_branch="docs/delta-fix/feature",
                base_branch="feature",
                pr_number=42,
                drift_summary="- `auth.md`: missing auth section",
            )

    assert result == 10
    _, kwargs = mock_client.post.call_args
    body = kwargs["json"]["body"]
    assert "### Drift Summary" in body
    assert "auth.md" in body
    assert "### Documentation Updates Summary" not in body


# Test that body includes updates summary section when updates_summary is provided
@pytest.mark.asyncio
async def test_create_docs_pull_request_with_updates_summary():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 11}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_docs_pull_request(
                installation_id=100,
                repo_full_name="owner/repo",
                head_branch="docs/delta-fix/feature",
                base_branch="feature",
                pr_number=42,
                updates_summary="- `auth.md`: added authentication section",
            )

    assert result == 11
    _, kwargs = mock_client.post.call_args
    body = kwargs["json"]["body"]
    assert "### Documentation Updates Summary" in body
    assert "auth.md" in body
    assert "### Drift Summary" not in body


# Test that body includes both sections when both summaries are provided
@pytest.mark.asyncio
async def test_create_docs_pull_request_with_both_summaries():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 12}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_docs_pull_request(
                installation_id=100,
                repo_full_name="owner/repo",
                head_branch="docs/delta-fix/feature",
                base_branch="feature",
                pr_number=42,
                drift_summary="- `auth.md`: missing section",
                updates_summary="- `auth.md`: added section",
            )

    assert result == 12
    _, kwargs = mock_client.post.call_args
    body = kwargs["json"]["body"]
    assert "### Drift Summary" in body
    assert "### Documentation Updates Summary" in body


# Test that create_docs_pull_request returns None when the PR already exists (422)
@pytest.mark.asyncio
async def test_create_docs_pull_request_already_exists():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Validation Failed"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_docs_pull_request(100, "owner/repo", "docs/branch", "main", 1)

    assert result is None


# Test that create_docs_pull_request returns None on unexpected API errors
@pytest.mark.asyncio
async def test_create_docs_pull_request_api_error():
    with patch(
        "app.services.github_api.repos.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_docs_pull_request(100, "owner/repo", "docs/branch", "main", 1)

    assert result is None


# Test that create_docs_pull_request returns None when an exception occurs
@pytest.mark.asyncio
async def test_create_docs_pull_request_exception():
    with patch(
        "app.services.github_api.repos.get_installation_access_token",
        new_callable=AsyncMock,
        side_effect=Exception("Network error"),
    ):
        result = await create_docs_pull_request(100, "owner/repo", "docs/branch", "main", 1)

    assert result is None
