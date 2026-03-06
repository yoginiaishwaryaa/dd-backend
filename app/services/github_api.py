import time
import jwt
import httpx
from pathlib import Path
from app.core.config import settings
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.drift import DriftEvent


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


# Fetches repository details from GitHub API
async def get_repo_details(installation_id: int, owner: str, repo_name: str):
    access_token = await get_installation_access_token(installation_id)

    async with httpx.AsyncClient() as client:
        repo_res = await client.get(
            f"https://api.github.com/repos/{owner}/{repo_name}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

        if repo_res.status_code != 200:
            raise Exception(f"GitHub API Error: {repo_res.text}")

        # Fetches details about the repository to display in dashboard
        data = repo_res.json()

        return {
            "name": data.get("full_name"),
            "description": data.get("description"),
            "language": data.get("language"),
            "stargazers_count": data.get("stargazers_count"),
            "forks_count": data.get("forks_count"),
            "avatar_url": (data.get("owner") or {}).get("avatar_url"),
        }


# Creates a GitHub Check Run for a PR
async def create_github_check_run(
    db: Session, drift_event_id, repo_full_name: str, head_sha: str, installation_id: int
):
    try:
        access_token = await get_installation_access_token(installation_id)

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"https://api.github.com/repos/{repo_full_name}/check-runs",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "name": "Delta Docs",
                    "head_sha": head_sha,
                    "status": "queued",  # Initial Status
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "output": {
                        "title": "PR Analysis Queued",
                        "summary": "Waiting for a worker to pick up the job...",
                    },
                },
            )

            if res.status_code != 201:
                print(f"Error creating check run: {res.text}")
                return None

            data = res.json()
            check_run_id = data.get("id")

            # Store check run ID so that status can be updated at different stages
            db.query(DriftEvent).filter(DriftEvent.id == drift_event_id).update(
                {"check_run_id": check_run_id}
            )
            db.commit()

            return check_run_id

    except Exception as e:
        print(f"Exception in create_github_check_run: {str(e)}")
        return None


# Creates a skipped check run if the linked repo is inactive
async def create_skipped_check_run(
    repo_full_name: str, head_sha: str, installation_id: int, reason: str
):
    try:
        access_token = await get_installation_access_token(installation_id)

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"https://api.github.com/repos/{repo_full_name}/check-runs",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "name": "Delta Docs",
                    "head_sha": head_sha,
                    "status": "completed",
                    "conclusion": "skipped",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "output": {
                        "title": "Analysis Skipped",
                        "summary": reason,
                    },
                },
            )

            if res.status_code != 201:
                print(f"Error creating skipped check run: {res.text}")

    except Exception as e:
        print(f"Exception in create_skipped_check_run: {str(e)}")


# Updates the GitHub Check Run status and output
async def update_github_check_run(
    repo_full_name: str,
    check_run_id: int,
    installation_id: int,
    status: str,
    conclusion: str | None = None,
    title: str | None = None,
    summary: str | None = None,
):
    try:
        access_token = await get_installation_access_token(installation_id)

        payload: dict = {"status": status}  # Setting the status of the check run

        if status == "completed" and conclusion:
            payload["conclusion"] = conclusion
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()

        # If title or summary is provided, including it in the output section of the check run
        if title or summary:
            payload["output"] = {}
            if title:
                payload["output"]["title"] = title
            if summary:
                payload["output"]["summary"] = summary

        async with httpx.AsyncClient() as client:
            res = await client.patch(
                f"https://api.github.com/repos/{repo_full_name}/check-runs/{check_run_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                json=payload,
            )

            if res.status_code != 200:
                print(f"Error updating check run: {res.text}")
                return False

            return True

    except Exception as e:
        print(f"Exception in update_github_check_run: {str(e)}")
        return False
