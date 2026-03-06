from datetime import timedelta
from app.core import security


# Test password hashing and verification
def test_hash_password():
    password = "secret_password"
    hashed = security.get_hash(password)
    assert hashed != password  # Hash should be different from plain text
    assert security.verify_hash(password, hashed) is True  # Correct password works
    assert security.verify_hash("wrong_password", hashed) is False  # Wrong password fails


# Test creating and verifying access tokens
def test_create_access_token():
    subject = "test_user_id"
    expires_delta = timedelta(minutes=15)
    token = security.create_access_token(subject, expires_delta)
    assert isinstance(token, str)

    # Decode and verify token contents
    payload = security.verify_token(token)
    assert payload is not None
    assert payload["sub"] == subject
    assert payload["type"] == "access"


# Test creating and verifying refresh tokens
def test_create_refresh_token():
    subject = "test_user_id"
    expires_delta = timedelta(days=7)
    token = security.create_refresh_token(subject, expires_delta)
    assert isinstance(token, str)

    # Decode and verify token contents
    payload = security.verify_token(token)
    assert payload is not None
    assert payload["sub"] == subject
    assert payload["type"] == "refresh"


# Test that expired tokens are rejected
def test_expired_token():
    subject = "test_user_id"
    expires_delta = timedelta(minutes=-1)  # Setting token as expired
    token = security.create_access_token(subject, expires_delta)

    payload = security.verify_token(token)
    assert payload is None  # Should return None for expired tokens


# Test that invalid tokens are rejected
def test_invalid_token():
    payload = security.verify_token("invalid_token_string")
    assert payload is None
