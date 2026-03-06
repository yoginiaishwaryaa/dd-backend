from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db_connection, get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationResponse

router = APIRouter()


# Endpoint to get all notifications for the current user
@router.get("/", response_model=list[NotificationResponse])
def get_notifications(
    db: Session = Depends(get_db_connection),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )


# Endpoint to mark a single notification as read
@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_as_read(
    notification_id: UUID,
    db: Session = Depends(get_db_connection),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    # Mark the notification as read
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


# Endpoint to mark all notifications as read
@router.patch("/read-all")
def mark_all_notifications_as_read(
    db: Session = Depends(get_db_connection),
    current_user: User = Depends(get_current_user),
):
    # Mark all notifications for the current user as read
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).update({"is_read": True})

    db.commit()
    return {"message": "All notifications marked as read"}


# Endpoint to delete a notification
@router.delete("/{notification_id}")
def delete_notification(
    notification_id: UUID,
    db: Session = Depends(get_db_connection),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notification)
    db.commit()
    return {"message": "Notification deleted"}


# Endpoint to delete all notifications for the current user
@router.delete("/")
def delete_all_notifications(
    db: Session = Depends(get_db_connection),
    current_user: User = Depends(get_current_user),
):
    db.query(Notification).filter(Notification.user_id == current_user.id).delete()

    db.commit()
    return {"message": "All notifications deleted"}
