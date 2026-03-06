import asyncio
import fnmatch
import subprocess
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import DriftEvent, CodeChange
from app.services.git_service import get_local_repo_path
from app.services.github_api import update_github_check_run
from app.services.notification_service import create_notification
from app.agents.state import DriftAnalysisState
from app.agents.graph import drift_analysis_graph


# Creates a separate SQLAlchemy session for use in background tasks
def _create_session():
    engine = create_engine(settings.POSTGRES_CONNECTION_URL, pool_pre_ping=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session()


# Extracts code changes and its metadata from git diff
def _extract_and_save_code_changes(session, drift_event):
    repo_full_name = drift_event.repository.repo_name
    base_sha = drift_event.base_sha
    head_sha = drift_event.head_sha

    # Get the locally cloned repo path
    repo_path = get_local_repo_path(repo_full_name)

    if not repo_path.exists():
        raise Exception(f"Local repository not found at {repo_path}")

    try:
        # Get a list of changed files using git diff
        result = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--name-status", f"{base_sha}...{head_sha}"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise Exception(f"Git diff failed: {result.stderr}")

        # Parse the git diff output and create CodeChange records
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status = parts[0]
            file_path = parts[1]

            # Map git file status to change_type
            change_type_map = {"A": "added", "M": "modified", "D": "deleted"}

            change_type = change_type_map.get(status, "modified")

            # Determine if the changed file is a code file (excluding common non-code files)
            non_code_extensions = {
                ".md",
                ".txt",
                ".rst",
                ".pdf",
                ".doc",
                ".docx",
                ".jpg",
                ".png",
                ".gif",
                ".svg",
                "LICENSE",
            }
            is_code = not any(file_path.lower().endswith(ext) for ext in non_code_extensions)

            # Check if file matches any of the repo's ignore patterns
            ignore_patterns: list[str] = drift_event.repository.file_ignore_patterns or []
            is_ignored = any(fnmatch.fnmatch(file_path, pattern) for pattern in ignore_patterns)

            # Create CodeChange record in DB
            code_change = CodeChange(
                drift_event_id=drift_event.id,
                file_path=file_path,
                change_type=change_type,
                is_code=is_code,
                is_ignored=is_ignored,
            )
            session.add(code_change)

        session.commit()

    except subprocess.TimeoutExpired:
        raise Exception(f"Timeout while extracting code changes for {repo_full_name}")
    except Exception as e:
        session.rollback()
        raise Exception(f"Error extracting code changes: {str(e)}")


# Main task that orchestrates the drift analysis process for a PR
def run_drift_analysis(drift_event_id: str):
    if not drift_event_id or drift_event_id == "None":
        print(f"ERROR: invalid drift_event_id: {drift_event_id!r}")
        return

    session = _create_session()

    try:
        drift_event = session.query(DriftEvent).filter(DriftEvent.id == drift_event_id).first()

        if not drift_event:
            print(f"Event {drift_event_id} not found in DB. Aborting.")
            return

        drift_event.processing_phase = "analyzing"
        drift_event.started_at = datetime.now(timezone.utc)
        session.commit()

        _extract_and_save_code_changes(session, drift_event)

        repo_path = get_local_repo_path(drift_event.repository.repo_name)

        initial_state: DriftAnalysisState = {
            "drift_event_id": str(drift_event.id),
            "base_sha": drift_event.base_sha,
            "head_sha": drift_event.head_sha,
            "session": session,
            "repo_path": str(repo_path),
            "docs_root_path": drift_event.repository.docs_root_path,
            "change_elements": [],
            "analysis_payloads": [],
            "findings": [],
        }

        drift_analysis_graph.invoke(initial_state)

    except Exception as e:
        print(f"ERROR: {e}")
        session.rollback()

        # Mark the event as failed and notify the user
        try:
            drift_event = session.query(DriftEvent).filter(DriftEvent.id == drift_event_id).first()
            if drift_event:
                drift_event.processing_phase = "failed"
                drift_event.drift_result = "error"
                drift_event.error_message = str(e)

                if drift_event.repository and drift_event.repository.installation:
                    repo = drift_event.repository
                    user_id = repo.installation.user_id

                    # Update the GitHub check run to reflect failure
                    if drift_event.check_run_id:
                        try:
                            asyncio.run(
                                update_github_check_run(
                                    repo_full_name=repo.repo_name,
                                    check_run_id=drift_event.check_run_id,
                                    installation_id=repo.installation_id,
                                    status="completed",
                                    conclusion="failure",
                                    title="Delta Drift Analysis",
                                    summary="Drift analysis failed due to an internal error.",
                                )
                            )
                        except Exception as check_run_e:
                            print(f"Failed to update check run on failure: {check_run_e}")

                    # Creating a notification for the failure of drift analysis
                    if user_id:
                        create_notification(
                            session,
                            user_id,
                            f"Drift analysis for PR #{drift_event.pr_number} in {repo.repo_name} failed.",
                        )

                session.commit()
        except Exception as inner_e:
            print(f"Failed to mark drift event as failed: {inner_e}")
            session.rollback()

        raise
    finally:
        session.close()
