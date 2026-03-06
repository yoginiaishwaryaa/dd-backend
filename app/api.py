from fastapi import APIRouter
from app.routers import auth, webhooks, repos, dashboard, notifications

# Main router
api_router = APIRouter()

# Mounting each feature router with its prefix
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(webhooks.router, prefix="/webhook", tags=["Webhooks"])
api_router.include_router(repos.router, prefix="/repos", tags=["Repositories"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
