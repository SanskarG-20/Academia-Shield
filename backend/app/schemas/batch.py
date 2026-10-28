"""
Pydantic Schemas for Batch Management.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

class BatchCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

class BatchUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None

class BatchJoinRequest(BaseModel):
    batch_code: str = Field(..., min_length=1, max_length=20)

class BatchMemberResponse(BaseModel):
    id: str
    student_id: str
    student_name: str
    student_email: str
    status: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

class BatchProfessorResponse(BaseModel):
    id: str
    professor_id: str
    name: str
    description: Optional[str]
    batch_code: str
    is_active: bool
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class BatchStudentResponse(BaseModel):
    """
    Student-facing batch response payload.
    STRICT SECURITY RULE: Never includes batch_code or member lists.
    """
    id: str
    name: str
    description: Optional[str]
    is_active: bool
    joined_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
