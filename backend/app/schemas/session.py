"""
Pydantic Schemas for Session Management.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

class SessionCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    start_at_utc: Optional[datetime] = None
    end_at_utc: Optional[datetime] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    timezone: str = Field(default="UTC")
    rule_set_id: Optional[str] = None
    recurrence_type: str = Field(default="none")
    recurrence_interval: int = Field(default=1)
    recurrence_days_of_week: Optional[list] = None
    recurrence_until_utc: Optional[datetime] = None
    idle_threshold_seconds: Optional[int] = Field(default=60, ge=5, le=3600)

class SessionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = None
    start_at_utc: Optional[datetime] = None
    end_at_utc: Optional[datetime] = None
    timezone: Optional[str] = None
    rule_set_id: Optional[str] = None
    status: Optional[str] = None
    idle_threshold_seconds: Optional[int] = Field(default=None, ge=5, le=3600)

class SessionStatusUpdate(BaseModel):
    status: str


class SessionResponse(BaseModel):
    id: str
    batch_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    start_at_utc: datetime
    end_at_utc: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    timezone: str
    status: str
    is_active: bool = False
    session_code: Optional[str] = None
    rule_set_id: Optional[str] = None
    policy_version: int = 1
    idle_threshold_seconds: int = 60
    recurrence_type: str = "none"
    recurrence_interval: int = 1
    recurrence_days_of_week: Optional[list] = None
    recurrence_until_utc: Optional[datetime] = None
    server_time_utc: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SessionStudentResponse(BaseModel):
    id: str
    batch_id: Optional[str] = None
    batch_name: Optional[str] = None
    professor_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    start_at_utc: datetime
    end_at_utc: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    timezone: str
    status: str
    is_active: bool = False
    is_joined: bool = False
    session_code: Optional[str] = None
    rule_set_id: Optional[str] = None
    policy_version: int = 1
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LiveMonitorStudentItem(BaseModel):
    student_id: str
    name: str
    participant_status: str
    presence_status: str
    enforcement_status: Optional[str] = "active"  # active, pending, restored, revoked, failed
    last_seen_at: str
    connection_source: str
    engagement_score: Optional[float] = None
    latest_activity: str
    violation_count: Optional[int] = 0
    policy_status: Optional[str] = "Active"  # Pending, Active, Restored, Failed
    usb_storage_status: Optional[str] = "Requires Managed Device"  # Active, Not Compliant, Requires Managed Device, Unsupported
    device_compliance_status: Optional[str] = "compliant"
    website_filtering_status: Optional[str] = "active"
    application_control_status: Optional[str] = "active"
    academic_activity_summary: Optional[Dict[str, Any]] = None
    blocked_website_attempts: Optional[int] = 0
    blocked_app_attempts: Optional[int] = 0
    engagement_state: Optional[str] = "Collecting Live Data"  # Collecting Live Data, Data Insufficient, High, Medium, Low, Final


class LiveMonitorResponse(BaseModel):
    session_id: str
    batch_name: Optional[str] = None
    session_title: Optional[str] = None
    policy_version: Optional[int] = 1
    status: str
    students: list[LiveMonitorStudentItem]
    online_count: int
    joined_count: int
    enforcing_count: Optional[int] = 0
    violation_count: int


class UnlockRequestCreate(BaseModel):
    issue_type: str = Field(default="technical_issue", description="unlock_request, technical_issue, emergency")
    description: str = Field(..., min_length=3, max_length=500)


class UnlockRequestResolve(BaseModel):
    status: str = Field(..., description="approved, rejected, resolved")
    resolution_notes: Optional[str] = None


class UnlockRequestResponse(BaseModel):
    id: str
    session_id: str
    student_id: str
    student_name: Optional[str] = None
    issue_type: str
    description: str
    status: str
    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)



