from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models.user import User
from app.models.installation import Installation
from app.models.repository import Repository
from app.services.git_service import remove_cloned_repository
from app.services.notification_service import create_notification
from app.services.github_webhook.repository_handlers import _insert_repositories


# Handle when GH app is first installed on a GitHub account
async def _handle_installation_created(db: Session, payload: dict):
    installation = payload["installation"]
    account = installation["account"]
    sender = payload["sender"]

    # Link installation to an existing user
    user = db.query(User).filter(User.github_user_id == sender["id"]).first()
    user_id = user.id if user else None

    values = {
        "installation_id": installation["id"],
        "account_name": account["login"],
        "account_type": account["type"],
    }
    if user_id:
        values["user_id"] = user_id

    # Upsert the installation
    stmt = insert(Installation).values(**values)

    update_dict = {
        "account_name": stmt.excluded.account_name,
        "account_type": stmt.excluded.account_type,
    }
    if user_id:
        update_dict["user_id"] = stmt.excluded.user_id

    stmt = stmt.on_conflict_do_update(index_elements=["installation_id"], set_=update_dict)
    db.execute(stmt)

    if payload.get("repositories"):
        await _insert_repositories(
            db, installation["id"], payload["repositories"], account.get("avatar_url")
        )

    # Create a notification for successful installation
    if user_id:
        num_repos = len(payload.get("repositories", []))
        repo_word = "repository" if num_repos == 1 else "repositories"
        create_notification(
            db,
            user_id,
            f"GitHub account {account['login']} connected to Delta with {num_repos} {repo_word}.",
        )


# Handle when GH app is uninstalled
def _handle_installation_deleted(db: Session, payload: dict):
    inst_id = payload["installation"]["id"]

    installation = db.query(Installation).filter(Installation.installation_id == inst_id).first()
    user_id = installation.user_id if installation else None

    repos = db.query(Repository).filter(Repository.installation_id == inst_id).all()

    for repo in repos:
        try:
            remove_cloned_repository(repo.repo_name)
        except Exception as e:
            print(f"Error removing repository {repo.repo_name}: {str(e)}")

    db.query(Installation).filter(Installation.installation_id == inst_id).delete(
        synchronize_session=False
    )

    # Create a notification for successful uninstallation
    if user_id:
        account_name = payload["installation"]["account"]["login"]
        create_notification(
            db,
            user_id,
            f"GitHub account {account_name} has been disconnected from Delta.",
        )


# Handle when installation is suspended or unsuspended
def _handle_installation_suspend(db: Session, payload: dict, suspended: bool):
    inst_id = payload["installation"]["id"]
    # Mark all repos as suspended/unsuspended
    db.query(Repository).filter(Repository.installation_id == inst_id).update(
        {"is_suspended": suspended}
    )
