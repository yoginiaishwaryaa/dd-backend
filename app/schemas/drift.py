import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# Schema for drift event list response (minimal data for table view)
class DriftEventListResponse(BaseModel):
    id: uuid.UUID
    pr_number: int
    base_branch: str
    head_branch: str
    processing_phase: str
    drift_result: str
    overall_drift_score: Optional[float]
    created_at: datetime
    docs_pr_number: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# Schema for drift finding response
class DriftFindingResponse(BaseModel):
    id: uuid.UUID
    code_path: str
    doc_file_path: Optional[str] = None
    change_type: Optional[str]
    drift_type: Optional[str]
    drift_score: Optional[float]
    explanation: Optional[str]
    confidence: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Schema for code change response
class CodeChangeResponse(BaseModel):
    id: uuid.UUID
    file_path: str
    change_type: Optional[str]
    is_code: Optional[bool]
    is_ignored: bool

    model_config = ConfigDict(from_attributes=True)


# Schema for drift event detail with nested findings and code changes
class DriftEventDetailResponse(DriftEventListResponse):
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    findings: list[DriftFindingResponse] = []
    code_changes: list[CodeChangeResponse] = []

    model_config = ConfigDict(from_attributes=True)
