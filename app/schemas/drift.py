import uuid
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# Structured output schema for the LLM drift assessment
class LLMDriftFinding(BaseModel):
    drift_detected: bool = Field(
        description="True if the documentation needs updating based on the code change."
    )
    drift_type: Literal["outdated_docs", "missing_docs", "ambiguous_docs", ""] = Field(
        default="", description="Type of drift detected. Empty string if no drift."
    )
    drift_score: float = Field(
        ge=0.0, le=1.0, description="Severity of the drift from 0.0 (none) to 1.0 (critical)."
    )
    explanation: str = Field(
        description="Clear, developer-friendly explanation of what changed and why docs are out of sync."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="How confident the LLM is in this assessment."
    )


# Schema for the drift event response
class DriftEventResponse(BaseModel):
    id: uuid.UUID
    pr_number: int
    base_branch: str
    head_branch: str
    processing_phase: str
    drift_result: str
    overall_drift_score: Optional[float]
    summary: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
