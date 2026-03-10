import time
import jwt
import httpx
from pathlib import Path
from app.core.config import settings


# Get GitHub installation Access Token with Signed JWT for API calls
async def get_installation_access_token(installation_id: int) -> str:
    # Load the Private Key from file
    try:
        key_path = Path(settings.GITHUB_PRIVATE_KEY_PATH)
        with open(key_path, "rb") as f:
            private_key = f.read()
    except FileNotFoundError:
        raise Exception(f"Private Key not found at {settings.GITHUB_PRIVATE_KEY_PATH}")

    # Create JWT and sign to authenticate as GitHub app
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued 60s in the past to account for clock skew
        "exp": now + (9 * 60),  # Expires in 9 minutes
        "iss": settings.GITHUB_APP_ID,
    }

    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    # Exchange the JWT for an installation token
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )

        if token_res.status_code != 201:
            raise Exception(f"Token Error: {token_res.text}")

        return token_res.json()["token"]
