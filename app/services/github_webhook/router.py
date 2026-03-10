from sqlalchemy.orm import Session

from app.services.github_webhook.installation_handlers import (
    _handle_installation_created,
    _handle_installation_deleted,
    _handle_installation_suspend,
)
from app.services.github_webhook.repository_handlers import (
    _handle_repos_added,
    _handle_repos_removed,
)
from app.services.github_webhook.pr_handlers import (
    _handle_pr_opened,
    _handle_pr_synchronize,
)
from app.services.github_webhook.check_suite_handlers import _handle_check_suite_rerequested


# Router to handle different types of GH webhook events
async def handle_github_event(db: Session, event_type: str, payload: dict):
    # Installation lifecycle events
    if event_type == "installation":
        action = payload.get("action")
        if action == "created":
            await _handle_installation_created(db, payload)
        elif action == "deleted":
            _handle_installation_deleted(db, payload)
        elif action == "suspend":
            _handle_installation_suspend(db, payload, suspended=True)
        elif action == "unsuspend":
            _handle_installation_suspend(db, payload, suspended=False)

    # Repo selection changes
    elif event_type == "installation_repositories":
        action = payload.get("action")
        if action == "added":
            await _handle_repos_added(db, payload)
        elif action == "removed":
            _handle_repos_removed(db, payload)

    # PR Events
    elif event_type == "pull_request":
        action = payload.get("action")
        if action == "opened":
            await _handle_pr_opened(db, payload)
        elif action == "synchronize":
            await _handle_pr_synchronize(db, payload)

    # Check Suite re-run request
    elif event_type == "check_suite":
        action = payload.get("action")
        if action == "rerequested":
            await _handle_check_suite_rerequested(db, payload)

    db.commit()
