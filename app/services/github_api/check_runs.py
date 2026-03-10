import httpx
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.drift import DriftEvent
from app.services.github_api.auth import get_installation_access_token


# Creates a GitHub Check Run for a PR
async def create_queued_check_run(
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
        print(f"Exception in create_queued_check_run: {str(e)}")
        return None


# Creates a skipped check run if the linked repo is inactive and if PR raised by Delta
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


# Creates a success check run
async def create_success_check_run(
    repo_full_name: str, head_sha: str, installation_id: int, title: str, summary: str
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
                    "conclusion": "success",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "output": {
                        "title": title,
                        "summary": summary,
                    },
                },
            )

            if res.status_code != 201:
                print(f"Error creating success check run: {res.text}")

    except Exception as e:
        print(f"Exception in create_success_check_run: {str(e)}")


# Updates the GitHub Check Run status and output
async def update_github_check_run(
    repo_full_name: str,
    check_run_id: int,
    installation_id: int,
    status: str,
    conclusion: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    details_url: str | None = None,
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

        # Link the Resolve button to Fix PR url if provided
        if details_url:
            payload["details_url"] = details_url

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
