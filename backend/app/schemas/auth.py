"""
Authentication Pydantic Schemas.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=100)
    role: str = Field(default="student")  # admin, professor, student, agent
    student_id: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("admin", "professor", "student", "agent"):
            raise ValueError("Role must be one of: admin, professor, student, agent")
        return clean

class LoginRequest(BaseModel):
    email: Optional[EmailStr] = None
    email_or_id: Optional[str] = None
    password: str = Field(..., min_length=1)
    device_name: Optional[str] = None
    device_identifier: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str
    user: Optional['UserResponse'] = None

class RefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    institutional_id: Optional[str] = None
    department: Optional[str] = None
    roll_number: Optional[str] = None
    year: Optional[str] = None
    designation: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdateRequest(BaseModel):
    """Editable, non-security-sensitive fields for the signed-in user."""

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    # The React client historically sends `name`; accept it during the API
    # migration and normalize it in the route.
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    department: Optional[str] = Field(default=None, max_length=100)
    institutional_id: Optional[str] = Field(default=None, max_length=100)
    roll_number: Optional[str] = Field(default=None, max_length=100)
    year: Optional[str] = Field(default=None, max_length=30)
    designation: Optional[str] = Field(default=None, max_length=100)
