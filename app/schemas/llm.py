from typing import Literal
from pydantic import BaseModel, Field


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


# Structured output schemas for the plan_updates LLM call
class PlannedUpdate(BaseModel):
    doc_path: str
    section: str
    action: str
    description: str


class UpdatePlan(BaseModel):
    updates: list[PlannedUpdate]
