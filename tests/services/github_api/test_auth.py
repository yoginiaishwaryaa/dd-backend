import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.github_api import get_installation_access_token


# =========== Fixtures ===========


# Auto mock settings (.env)
@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.services.github_api.auth.settings") as mock:
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
    with patch("app.services.github_api.auth.jwt.encode") as mock:
        mock.return_value = "dummy_jwt"
        yield mock


# =========== get_installation_access_token Tests ===========


# Test that we can get an installation token successfully
@pytest.mark.asyncio
async def test_get_installation_access_token_success():
    with patch("app.services.github_api.auth.httpx.AsyncClient") as mock_client:
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
    with patch("app.services.github_api.auth.httpx.AsyncClient") as mock_client:
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
