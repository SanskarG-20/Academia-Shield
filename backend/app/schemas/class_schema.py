"""
Class Pydantic Schemas.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

class ClassCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    course_code: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None

class ClassResponse(BaseModel):
    id: str
    professor_id: str
    name: str
    course_code: str
    description: Optional[str]
    created_at: datetime
    student_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)

class AddStudentRequest(BaseModel):
    student_email_or_id: str
