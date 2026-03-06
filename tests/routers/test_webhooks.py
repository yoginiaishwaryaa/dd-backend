import pytest
import hmac
import hashlib
import json
from unittest.mock import MagicMock, AsyncMock
from app.core.config import settings
from app.routers.webhooks import validate_github_signature
from fastapi import Request, HTTPException


# Test that valid GH signatures pass validation
@pytest.mark.asyncio
async def test_validate_github_signature_valid():
    payload = {"test": "data"}
    body = json.dumps(payload).encode()

    # Generate a valid signature using GH webhook secret
    signature = (
        "sha256="
        + hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )

    mock_request = MagicMock(spec=Request)
    mock_request.headers.get.return_value = signature
    mock_request.body = AsyncMock(return_value=body)

    result = await validate_github_signature(mock_request)
    assert result


# Test that requests without signature are rejected
@pytest.mark.asyncio
async def test_validate_github_signature_missing():
    mock_request = MagicMock(spec=Request)
    mock_request.headers.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await validate_github_signature(mock_request)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Missing signature"


# Test that requests with invalid signatures are rejected
@pytest.mark.asyncio
async def test_validate_github_signature_invalid():
    body = json.dumps({"test": "data"}).encode()

    mock_request = MagicMock(spec=Request)
    mock_request.headers.get.return_value = "sha256=invalidsignature"
    mock_request.body = AsyncMock(return_value=body)

    with pytest.raises(HTTPException) as exc_info:
        await validate_github_signature(mock_request)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid signature"
