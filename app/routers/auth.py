import httpx
from datetime import timedelta
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, Depends, Response, Request, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.core import security
from app.models.user import User
from app.core.config import settings
from app.models.installation import Installation
from app.deps import get_db_connection, get_current_user

router = APIRouter()


# Endpoint to create a new user account with email & password
@router.post("/signup", response_model=schemas.Message)
def create_user(user_in: schemas.UserCreate, db: Session = Depends(get_db_connection)):
    # Check if user already exists
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="User with this email already exists.",
        )

    # Creates new user with hashed password and commits in DB
    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        password_hash=security.get_hash(user_in.password),
    )

    db.add(user)
    db.commit()
    return {"message": "User created successfully"}


# Endpoint to Login with email & password
@router.post("/login", response_model=schemas.UserLoginResponse)
def login(response: Response, user_in: schemas.UserLogin, db: Session = Depends(get_db_connection)):
    # Verify credentials
    user = db.query(User).filter(User.email == user_in.email).first()
    if (
        not user
        or not user.password_hash
        or not security.verify_hash(user_in.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Incorrect credentials.")

    # Generate access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(user.id, expires_delta=access_token_expires)

    # Generate refresh token
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = security.create_refresh_token(user.id, expires_delta=refresh_token_expires)

    # Store the refresh token hash in DB for validation (during refresh logic)
    user.current_refresh_token_hash = security.get_hash(refresh_token)
    db.commit()

    # Send both tokens as httponly (To prevent XSS Scripting) cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=int(access_token_expires.total_seconds()),
        expires=int(access_token_expires.total_seconds()),
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=int(refresh_token_expires.total_seconds()),
        expires=int(refresh_token_expires.total_seconds()),
    )

    return {"email": user.email, "name": user.full_name}


# Endpoint for the user to Logout
@router.post("/logout", response_model=schemas.Message)
def logout(response: Response, request: Request, db: Session = Depends(get_db_connection)):
    user_id = None

    # Get user id from Access token (if fails then from refresh token)
    access_token = request.cookies.get("access_token")
    if access_token:
        payload = security.verify_token(access_token)
        if payload:
            user_id = payload.get("sub")

    if not user_id:
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            payload = security.verify_token(refresh_token)
            if payload:
                user_id = payload.get("sub")

    # Clear the stored refresh token hash from DB
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.current_refresh_token_hash = None
            db.commit()

    # Delete the cookies on user end
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")

    return {"message": "Logout successful"}


# Endpoint to handle GitHub OAuth callback after user authorises the GitHub app
@router.get("/github/callback")
async def github_callback(
    request: Request,
    db: Session = Depends(get_db_connection),
    current_user: User = Depends(get_current_user),
):
    code = request.query_params.get("code")
    installation_id = request.query_params.get("installation_id")

    GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID
    GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET

    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing")

    async with httpx.AsyncClient() as client:
        # Get Access Token from GitHub
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
        )
        token_data = token_response.json()

        if "error" in token_data:
            error_code = token_data.get("error")
            description = token_data.get("error_description", "No description provided")
            raise HTTPException(
                status_code=400, detail=f"GitHub Error: {error_code} - {description}"
            )

        access_token = token_data["access_token"]

        # Fetch the GitHub user profile
        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        github_user_data = user_response.json()

    # Link the GitHub account to user in DB
    current_user.github_user_id = github_user_data["id"]
    current_user.github_username = github_user_data["login"]

    # If installation ID received then links it to the user
    if installation_id:
        install_id_int = int(installation_id)

        existing_install = (
            db.query(Installation).filter(Installation.installation_id == install_id_int).first()
        )

        if existing_install:
            existing_install.user_id = current_user.id
        else:
            new_install = Installation(
                installation_id=install_id_int,
                user_id=current_user.id,
                account_name=github_user_data["login"],
                account_type="User",
            )
            db.add(new_install)

    db.commit()

    return RedirectResponse(url=f"{settings.FRONTEND_URL}/dashboard", status_code=303)
