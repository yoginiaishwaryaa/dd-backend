import hmac
import hashlib
from app.core.config import settings
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.deps import get_db_connection
from app.services.github_webhook_service import handle_github_event

router = APIRouter()


# Verifies that webhook event actually came from GitHub (Check based on GitHub Webhook Secret)
async def validate_github_signature(request: Request):
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing signature")

    body = await request.body()

    # Compute expected signature using stored webhook secret
    expected_signature = (
        "sha256="
        + hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )

    # Compare the expected and received signatures
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    return True


# Main webhook endpoint that receives all GitHub events
@router.post("/github")
async def github_webhook_handler(request: Request, db: Session = Depends(get_db_connection)):
    await validate_github_signature(request)
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")

    if not event_type:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    try:
        # Route the webhook event to the appropriate handler
        await handle_github_event(db, event_type, payload)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return {"status": "Received and Processed Event"}
