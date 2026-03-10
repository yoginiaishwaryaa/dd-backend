import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.github_webhook import handle_github_event
from app.models.installation import Installation
from app.models.drift import DriftEvent


# =========== Helper Functions ===========


# Helper function to create a check_suite rerequested payload
def _make_check_suite_payload(head_sha="sha999", repo_full_name="owner/repo", installation_id=100):
    return {
        "action": "rerequested",
        "check_suite": {"head_sha": head_sha},
        "repository": {"full_name": repo_full_name},
        "installation": {"id": installation_id},
    }


# Helper function that returns a mock db whose DriftEvent query chain returns drift_event
def _make_check_suite_db(drift_event):
    mock_db = MagicMock()
    (
        mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value
    ) = drift_event
    return mock_db


# =========== check_suite_rerequested Tests ===========


# Test that check_suite rerequested with valid payload resets drift event and re-enqueues analysis
@pytest.mark.asyncio
async def test_check_suite_rerequested_resets_and_requeues():
    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    drift_event.head_sha = "sha999"
    mock_db = _make_check_suite_db(drift_event)
    payload = _make_check_suite_payload()

    with (
        patch(
            "app.services.github_webhook.check_suite_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ) as mock_create_check_run,
        patch("app.services.github_webhook.check_suite_handlers.task_queue") as mock_task_queue,
        patch("app.services.github_webhook.check_suite_handlers.run_drift_analysis") as mock_run,
    ):
        await handle_github_event(mock_db, "check_suite", payload)

    mock_create_check_run.assert_called_once_with(
        mock_db, str(drift_event.id), "owner/repo", drift_event.head_sha, 100
    )
    mock_task_queue.enqueue.assert_called_once_with(mock_run, str(drift_event.id))


# Test that missing head_sha in payload causes early return without touching DB
@pytest.mark.asyncio
async def test_check_suite_rerequested_missing_head_sha():
    mock_db = MagicMock()
    payload = {
        "check_suite": {},  # no head_sha
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 100},
    }

    with patch("app.services.github_webhook.check_suite_handlers.task_queue") as mock_task_queue:
        await handle_github_event(mock_db, "check_suite", payload)

    mock_db.flush.assert_not_called()
    mock_task_queue.enqueue.assert_not_called()


# Test that a missing installation_id causes early return
@pytest.mark.asyncio
async def test_check_suite_rerequested_missing_installation_id():
    mock_db = MagicMock()
    payload = {
        "check_suite": {"head_sha": "sha999"},
        "repository": {"full_name": "owner/repo"},
        "installation": {},  # no id
    }

    with patch("app.services.github_webhook.check_suite_handlers.task_queue") as mock_task_queue:
        await handle_github_event(mock_db, "check_suite", payload)

    mock_db.flush.assert_not_called()
    mock_task_queue.enqueue.assert_not_called()


# Test that when no drift event is found for the head_sha, nothing is re-enqueued
@pytest.mark.asyncio
async def test_check_suite_rerequested_no_drift_event_found():
    mock_db = _make_check_suite_db(None)  # that is when first() returns None
    payload = _make_check_suite_payload()

    with patch("app.services.github_webhook.check_suite_handlers.task_queue") as mock_task_queue:
        await handle_github_event(mock_db, "check_suite", payload)

    mock_db.flush.assert_not_called()
    mock_task_queue.enqueue.assert_not_called()


# Test that stale DriftFindings and CodeChanges are deleted before re-queuing
@pytest.mark.asyncio
async def test_check_suite_rerequested_clears_stale_findings_and_changes():
    from app.models.drift import DriftFinding, CodeChange

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    mock_db = _make_check_suite_db(drift_event)
    payload = _make_check_suite_payload()

    deleted_models = []

    def track_deletes(model):
        m = MagicMock()
        m.filter.return_value.delete = MagicMock(
            side_effect=lambda **kw: deleted_models.append(model)
        )
        m.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
            drift_event
        )
        return m

    mock_db.query.side_effect = track_deletes

    with (
        patch(
            "app.services.github_webhook.check_suite_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.check_suite_handlers.task_queue"),
    ):
        await handle_github_event(mock_db, "check_suite", payload)

    assert DriftFinding in deleted_models
    assert CodeChange in deleted_models


# Test that all drift event fields are reset to clean queued state
@pytest.mark.asyncio
async def test_check_suite_rerequested_resets_drift_event_fields():
    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    mock_db = _make_check_suite_db(drift_event)
    payload = _make_check_suite_payload()

    with (
        patch(
            "app.services.github_webhook.check_suite_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.check_suite_handlers.task_queue"),
    ):
        await handle_github_event(mock_db, "check_suite", payload)

    assert drift_event.processing_phase == "queued"
    assert drift_event.drift_result == "pending"
    assert drift_event.overall_drift_score is None
    assert drift_event.summary is None
    assert drift_event.error_message is None
    assert drift_event.started_at is None
    assert drift_event.completed_at is None
    assert drift_event.check_run_id is None
    mock_db.flush.assert_called_once()


# Test that unrelated check_suite actions are ignored
@pytest.mark.asyncio
async def test_check_suite_non_rerequested_action_ignored():
    mock_db = MagicMock()
    payload = {
        "action": "completed",
        "check_suite": {"head_sha": "sha999"},
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 100},
    }

    with patch("app.services.github_webhook.check_suite_handlers.task_queue") as mock_task_queue:
        await handle_github_event(mock_db, "check_suite", payload)

    mock_task_queue.enqueue.assert_not_called()


# =========== Notification Tests ===========


# Test notification is sent when drift analysis is re-queued via check suite re-request
@pytest.mark.asyncio
async def test_notification_on_check_suite_rerequested():
    user_id = uuid.uuid4()

    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    drift_event.pr_number = 22
    drift_event.head_sha = "sha999"

    mock_installation = MagicMock()
    mock_installation.user_id = user_id

    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        if model == DriftEvent:
            m.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
                drift_event
            )
        elif model == Installation:
            m.filter.return_value.first.return_value = mock_installation
        else:
            m.filter.return_value.delete.return_value = None
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_side_effect
    payload = _make_check_suite_payload(
        head_sha="sha999", repo_full_name="owner/repo", installation_id=100
    )

    with (
        patch(
            "app.services.github_webhook.check_suite_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.check_suite_handlers.task_queue"),
        patch("app.services.github_webhook.check_suite_handlers.create_notification") as mock_notif,
    ):
        await handle_github_event(mock_db, "check_suite", payload)

    mock_notif.assert_called_once()
    _, notif_user_id, content = mock_notif.call_args[0]
    assert notif_user_id == user_id
    assert "PR #22" in content
    assert "owner/repo" in content
    assert "re-queued" in content


# Test no notification on check suite rerequested when no user_id
@pytest.mark.asyncio
async def test_no_notification_on_check_suite_rerequested_when_no_user_id():
    drift_event = MagicMock()
    drift_event.id = uuid.uuid4()
    drift_event.pr_number = 22
    drift_event.head_sha = "sha999"

    mock_installation = MagicMock()
    mock_installation.user_id = None

    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        if model == DriftEvent:
            m.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
                drift_event
            )
        elif model == Installation:
            m.filter.return_value.first.return_value = mock_installation
        else:
            m.filter.return_value.delete.return_value = None
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_side_effect
    payload = _make_check_suite_payload()

    with (
        patch(
            "app.services.github_webhook.check_suite_handlers.create_queued_check_run",
            new_callable=AsyncMock,
        ),
        patch("app.services.github_webhook.check_suite_handlers.task_queue"),
        patch("app.services.github_webhook.check_suite_handlers.create_notification") as mock_notif,
    ):
        await handle_github_event(mock_db, "check_suite", payload)

    mock_notif.assert_not_called()
