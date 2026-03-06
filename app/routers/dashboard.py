from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.deps import get_db_connection, get_current_user
from app.models.user import User
from app.models.installation import Installation
from app.models.repository import Repository
from app.models.drift import DriftEvent
from app.services.github_api import get_repo_details

router = APIRouter()


# Endpoint to get dashboard stats - Counts of installations, Count of Linked repos, Number of drift events, Number of Raised PRs
@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db_connection), current_user: User = Depends(get_current_user)
):
    # Counts number of installations for the user
    installations_count = int(
        db.query(func.count(Installation.id))
        .filter(Installation.user_id == current_user.id)
        .scalar()
        or 0
    )

    # Counts the number of linked repos across all installations
    repos_count = int(
        db.query(func.count(Repository.id))
        .join(Installation, Repository.installation_id == Installation.installation_id)
        .filter(Installation.user_id == current_user.id)
        .scalar()
        or 0
    )

    # Counts the number of  drift events across all repos
    drift_events_count = int(
        db.query(func.count(DriftEvent.id))
        .join(Repository, DriftEvent.repo_id == Repository.id)
        .join(Installation, Repository.installation_id == Installation.installation_id)
        .filter(Installation.user_id == current_user.id)
        .scalar()
        or 0
    )

    # TODO: Implement logic to calculate the count of PRs raised for review
    pr_waiting_count = 0

    return {
        "installations_count": installations_count,
        "repos_linked_count": repos_count,
        "drift_events_count": drift_events_count,
        "pr_waiting_count": pr_waiting_count,
    }


# Endpoint to get the 5 most recent linked repos and its details
@router.get("/repos")
async def get_dashboard_repos(
    db: Session = Depends(get_db_connection), current_user: User = Depends(get_current_user)
):
    recent_repos = (
        db.query(Repository)
        .join(Installation, Repository.installation_id == Installation.installation_id)
        .filter(Installation.user_id == current_user.id)
        .order_by(Repository.created_at.desc())
        .limit(5)
        .all()
    )

    results = []
    for repo in recent_repos:
        # Parse owner/repo from full name
        repo_owner, repo_name = repo.repo_name.split("/")
        try:
            # Fetch live data from GitHub API
            if not repo.installation_id:
                raise ValueError("No installation ID for repository")
            details = await get_repo_details(repo.installation_id, repo_owner, repo_name)
            results.append(details)
        except Exception:
            # Fallback if GitHub API fails
            results.append(
                {
                    "name": repo.repo_name,
                    "description": "Error fetching details",
                    "language": "Unknown",
                    "stargazers_count": 0,
                    "forks_count": 0,
                    "avatar_url": None,
                }
            )

    return results
