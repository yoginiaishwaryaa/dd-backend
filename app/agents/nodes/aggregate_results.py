import asyncio
from typing import Any
from datetime import datetime, timezone

from app.db.base import DriftEvent, DriftFinding
from app.services.github_api import update_github_check_run
from app.services.notification_service import create_notification
from app.agents.state import DriftAnalysisState


# Node persists all findings to the DB and updates the GH Check Run
def aggregate_results(state: DriftAnalysisState) -> dict[str, Any]:
    session = state["session"]
    drift_event_id = state["drift_event_id"]
    findings: list[dict] = state["findings"]

    # Determine overall drift score and conclusion from all findings
    if not findings:
        overall_score = 0.0
        drift_result = "clean"
    else:
        overall_score = max(f.get("drift_score", 0.0) for f in findings)
        has_missing = any(f.get("drift_type") == "missing_docs" for f in findings)
        drift_result = "missing_docs" if has_missing else "drift_detected"

    # Build a human readable summary for the GH Check Run output
    if drift_result == "clean":
        summary = "No documentation drift detected."
    else:
        drift_types = set(f.get("drift_type", "") for f in findings)
        summary = (
            f"Found {len(findings)} documentation drift(s)\n\n"
            f"Drift types: {', '.join(drift_types)}\n\n"
        )
        for i, f in enumerate(findings, 1):
            summary += f"{i}. {f.get('code_path', '?')} - {f.get('drift_type', '?')} (score: {f.get('drift_score', 0):.1f})\n"
            summary += f"   {f.get('explanation', '')}\n\n"

    # Add each finding as a DriftFinding record in DB
    for f in findings:
        doc_paths = f.get("matched_doc_paths", [])
        doc_file_path = doc_paths[0] if doc_paths else None

        finding = DriftFinding(
            drift_event_id=drift_event_id,
            code_path=f.get("code_path", ""),
            doc_file_path=doc_file_path,
            change_type=f.get("change_type"),
            drift_type=f.get("drift_type"),
            drift_score=f.get("drift_score"),
            explanation=f.get("explanation"),
            confidence=f.get("confidence"),
        )
        session.add(finding)

    # Update the drift event record with the final score, conclusion and logs
    drift_event = session.query(DriftEvent).filter(DriftEvent.id == drift_event_id).first()

    if drift_event:
        drift_event.overall_drift_score = overall_score
        drift_event.drift_result = drift_result
        drift_event.summary = summary
        drift_event.processing_phase = "completed"
        drift_event.completed_at = datetime.now(timezone.utc)

        if drift_event.repository and drift_event.repository.installation:
            user_id = drift_event.repository.installation.user_id
            if user_id:
                repo_name = drift_event.repository.repo_name
                pr_number = drift_event.pr_number
                if drift_result == "clean":
                    notif_content = f"Drift analysis for PR #{pr_number} in {repo_name} completed - No documentation drift detected."
                elif drift_result == "missing_docs":
                    notif_content = f"Drift analysis for PR #{pr_number} in {repo_name} completed - Missing documentation detected (score: {overall_score:.2f})."
                else:
                    notif_content = f"Drift analysis for PR #{pr_number} in {repo_name} completed - Documentation drift detected (score: {overall_score:.2f})."
                create_notification(session, user_id, notif_content)

        session.commit()
    else:
        print(f"DriftEvent {drift_event_id} not found in DB")
        session.commit()

    # Push the final result to GH as a completed Check Run
    if drift_event and drift_event.check_run_id:
        repo = drift_event.repository
        repo_full_name = repo.repo_name
        installation_id = repo.installation_id
        check_run_id = drift_event.check_run_id

        conclusion = "success" if drift_result == "clean" else "action_required"
        title = "Delta Drift Analysis"

        try:
            asyncio.run(
                update_github_check_run(
                    repo_full_name=repo_full_name,
                    check_run_id=check_run_id,
                    installation_id=installation_id,
                    status="completed",
                    conclusion=conclusion,
                    title=title,
                    summary=summary,
                )
            )
        except Exception as exc:
            print(f"GitHub Check Run update failed: {exc}")

    return {"findings": []}
