from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BugPriority, BugStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BugCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    priority: BugPriority = BugPriority.medium


class BugUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: BugStatus | None = None
    priority: BugPriority | None = None


class BugOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: BugStatus
    priority: BugPriority
    reporter_id: int
    created_at: datetime
    updated_at: datetime
