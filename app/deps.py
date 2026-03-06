from typing import Generator
from datetime import timedelta
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.db.session import SessionLocal


# Dependency to get a DB session for each request
def get_db_connection() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


# Dependency to check and verify auth and get the current user
def get_current_user(
    request: Request, response: Response, db: Session = Depends(get_db_connection)
):
    # First tries verification with the access token from cookies
    access_token = request.cookies.get("access_token")

    if access_token:
        payload = security.verify_token(access_token)
        if payload and payload.get("type") == "access":
            user_id = payload.get("sub")
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user

    # If access token fails, verifies through refresh token
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = security.verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Makes sure the refresh token matches refresh token hash stored in DB
    if not user.current_refresh_token_hash or not security.verify_hash(
        refresh_token, user.current_refresh_token_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Generate and set fresh access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = security.create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )

    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        max_age=int(access_token_expires.total_seconds()),
        expires=int(access_token_expires.total_seconds()),
    )

    return user
