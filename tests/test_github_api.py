import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.github_api import get_repo_details, get_installation_access_token


# Auto mock settings (.env)
@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.services.github_api.settings") as mock:
        mock.GITHUB_PRIVATE_KEY_PATH = "dummy_path"
        mock.GITHUB_APP_ID = "dummy_app_id"
        yield mock


# Auto mock private key reading
@pytest.fixture(autouse=True)
def mock_file_read():
    with patch("builtins.open", new_callable=MagicMock) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = b"dummy_private_key"
        yield mock_open


# Auto mock JWT encoding
@pytest.fixture(autouse=True)
def mock_jwt():
    with patch("app.services.github_api.jwt.encode") as mock:
        mock.return_value = "dummy_jwt"
        yield mock


# Test that we can get an installation token successfully
@pytest.mark.asyncio
async def test_get_installation_access_token_success():
    with patch("app.services.github_api.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        # Mock GH token response
        mock_token_response = MagicMock()
        mock_token_response.status_code = 201
        mock_token_response.json.return_value = {"token": "access_token"}

        mock_client_instance.post.return_value = mock_token_response

        token = await get_installation_access_token(123)
        assert token == "access_token"


# Test that token errors are handled properly
@pytest.mark.asyncio
async def test_get_installation_access_token_error():
    with patch("app.services.github_api.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        # Mock a failed response from GH
        mock_token_response = MagicMock()
        mock_token_response.status_code = 400
        mock_token_response.text = "Bad Request"

        mock_client_instance.post.return_value = mock_token_response

        # Should raise an exception
        with pytest.raises(Exception) as exc:
            await get_installation_access_token(123)
        assert "Token Error" in str(exc.value)


# Test fetching repo details from GH API
@pytest.mark.asyncio
async def test_get_repo_details_success():
    with patch(
        "app.services.github_api.get_installation_access_token", new_callable=AsyncMock
    ) as mock_get_token:
        mock_get_token.return_value = "mock_token"

        with patch("app.services.github_api.httpx.AsyncClient") as mock_client:
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
