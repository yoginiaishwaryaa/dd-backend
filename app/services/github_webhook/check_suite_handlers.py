from sqlalchemy.orm import Session

from app.models.installation import Installation
from app.models.drift import DriftEvent, DriftFinding, CodeChange
from app.services.github_api import create_queued_check_run
from app.core.queue import task_queue
from app.services.drift_analysis import run_drift_analysis
from app.services.notification_service import create_notification


# Handle when a user clicks "Re-run all checks" in the linked repo
async def _handle_check_suite_rerequested(db: Session, payload: dict):
    check_suite = payload.get("check_suite", {})
    head_sha = check_suite.get("head_sha")
    repo_full_name = payload.get("repository", {}).get("full_name")
    installation_id = payload.get("installation", {}).get("id")

    if not head_sha or not repo_full_name or not installation_id:
        print("Warning: Missing fields in check_suite rerequested payload.")
        return

    # Find latest existing drift event by its head_sha
    drift_event = (
        db.query(DriftEvent)
        .join(DriftEvent.repository)
        .filter(DriftEvent.head_sha == head_sha)
        .order_by(DriftEvent.created_at.desc())
        .first()
    )

    if not drift_event:
        print(f"Warning: No DriftEvent found for head_sha {head_sha}.")
        return

    drift_event_id = str(drift_event.id)

    # Clear all stale findings and code changes from previous run
    db.query(DriftFinding).filter(DriftFinding.drift_event_id == drift_event.id).delete(
        synchronize_session=False
    )
    db.query(CodeChange).filter(CodeChange.drift_event_id == drift_event.id).delete(
        synchronize_session=False
    )

    # Reset the drift event back to a clean queued state
    drift_event.processing_phase = "queued"
    drift_event.drift_result = "pending"
    drift_event.overall_drift_score = None
    drift_event.summary = None
    drift_event.error_message = None
    drift_event.started_at = None
    drift_event.completed_at = None
    drift_event.check_run_id = None
    db.flush()

    # Create a fresh GitHub check run
    await create_queued_check_run(
        db, drift_event_id, repo_full_name, drift_event.head_sha, installation_id
    )

    # Re-enqueue the drift analysis job
    task_queue.enqueue(run_drift_analysis, drift_event_id)

    # Notify the user that drift analysis has been re-queued on their request
    installation = (
        db.query(Installation).filter(Installation.installation_id == installation_id).first()
    )
    if installation and installation.user_id:
        create_notification(
            db,
            installation.user_id,
            f"PR #{drift_event.pr_number} in {repo_full_name} has been re-queued on request for drift analysis.",
        )
