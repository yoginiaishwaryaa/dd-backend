from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from app.core.config import settings

# Initialize FastAPI App
app = FastAPI(title=settings.PROJECT_NAME)

# Setup CORS to allow frontend to hit endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set prefix of all routes to be /api
app.include_router(api_router, prefix="/api")


# Basic Health Check Endpoint
@app.get("/api")
def read_root():
    return {"message": "Delta is up and running... :)"}
