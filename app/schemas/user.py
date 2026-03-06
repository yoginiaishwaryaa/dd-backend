from pydantic import BaseModel, ConfigDict, EmailStr
from uuid import UUID
from datetime import datetime


# Base user fields shared across schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None


# Schema for creating a new user
class UserCreate(UserBase):
    password: str


# Schema for login request
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Schema for returning user data
class User(UserBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)  # Allow creation by ORM models


# Schema for login response
class UserLoginResponse(BaseModel):
    email: EmailStr
    name: str
