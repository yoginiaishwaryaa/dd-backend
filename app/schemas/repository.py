from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional


# Base Repository schema
class RepositoryBase(BaseModel):
    repo_name: str


# Schema for updating repository settings
class RepositorySettings(BaseModel):
    docs_root_path: Optional[str] = None
    target_branch: Optional[str] = None
    style_preference: Optional[str] = None
    file_ignore_patterns: Optional[list[str]] = None
    reviewer: Optional[str] = None


# Schema for toggling repo active status
class RepositoryActivation(BaseModel):
    is_active: bool


# Schema for returning full repository data
class RepositoryResponse(BaseModel):
    id: UUID
    repo_name: str
    is_active: bool  # User controlled
    is_suspended: bool  # System controlled
    avatar_url: Optional[str]
    docs_root_path: Optional[str]
    target_branch: Optional[str]
    style_preference: Optional[str]
    file_ignore_patterns: Optional[list[str]]
    reviewer: Optional[str]
    last_synced_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
