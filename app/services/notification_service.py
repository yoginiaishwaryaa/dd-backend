import uuid
from sqlalchemy.orm import Session
from app.models.notification import Notification


# Creates a notification for a user in the DB
def create_notification(db: Session, user_id: uuid.UUID, content: str) -> None:
    notification = Notification(user_id=user_id, content=content)
    db.add(notification)
