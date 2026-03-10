from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models.installation import Installation
from app.models.repository import Repository
from app.services.github_api import get_installation_access_token
from app.services.git_service import clone_repository, remove_cloned_repository
from app.services.notification_service import create_notification


# Upsert repositories (Insert if they don't exist or update existing repos)
async def _insert_repositories(
    db: Session, installation_id: int, repos_list: list, account_avatar_url: str | None = None
):
    if not repos_list:
        return

    values_list = []
    for repo in repos_list:
        values_list.append(
            {
                "installation_id": installation_id,
                "repo_name": repo["full_name"],
                "is_active": True,
                "avatar_url": account_avatar_url,
            }
        )

    # Insert or update on conflict
    stmt = insert(Repository).values(values_list)
    stmt = stmt.on_conflict_do_update(
        index_elements=["installation_id", "repo_name"],
        set_={"is_active": True, "avatar_url": stmt.excluded.avatar_url},
    )
    db.execute(stmt)

    try:
        access_token = await get_installation_access_token(installation_id)
        for repo in repos_list:
            repo_full_name = repo["full_name"]
            await clone_repository(repo_full_name, access_token)
    except Exception as e:
        print(f"Error cloning repositories for installation {installation_id}: {str(e)}")


# Handle when repos are added to an existing installation
async def _handle_repos_added(db: Session, payload: dict):
    inst_id = payload["installation"]["id"]
    repos = payload["repositories_added"]
    account_avatar_url = payload["installation"]["account"].get("avatar_url")
    await _insert_repositories(db, inst_id, repos, account_avatar_url)

    # Create a notification for new repos added
    installation = db.query(Installation).filter(Installation.installation_id == inst_id).first()
    if installation and installation.user_id:
        for repo in repos:
            create_notification(
                db,
                installation.user_id,
                f"Repository {repo['full_name']} has been successfully linked to Delta.",
            )


# Handle when repos are removed from an existing installation
def _handle_repos_removed(db: Session, payload: dict):
    inst_id = payload["installation"]["id"]
    repos = payload["repositories_removed"]

    installation = db.query(Installation).filter(Installation.installation_id == inst_id).first()
    user_id = installation.user_id if installation else None

    repo_full_names = [repo["full_name"] for repo in repos]

    if repo_full_names:
        for repo_name in repo_full_names:
            try:
                remove_cloned_repository(repo_name)
            except Exception as e:
                print(f"Error removing repository {repo_name}: {str(e)}")

        db.query(Repository).filter(
            Repository.installation_id == inst_id, Repository.repo_name.in_(repo_full_names)
        ).delete(synchronize_session=False)

        # Create a notification for repos removed
        if user_id:
            for repo_name in repo_full_names:
                create_notification(
                    db,
                    user_id,
                    f"Repository {repo_name} has been successfully unlinked from Delta.",
                )
