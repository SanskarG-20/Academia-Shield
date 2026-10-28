"""
Dashboard Pydantic Schemas.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

class LiveDashboardResponse(BaseModel):
    active_sessions_count: int
    enrolled_devices_count: int
    online_agents_count: int
    total_violations_today: int
    active_sessions: List[Dict[str, Any]] = []

class ViolationResponse(BaseModel):
    id: str
    device_id: str
    student_name: Optional[str]
    session_id: Optional[str]
    session_title: Optional[str]
    violation_type: str
    target_value: str
    action_taken: str
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AgentStatusResponse(BaseModel):
    device_id: str
    user_name: str
    user_email: str
    device_name: str
    platform: str
    agent_version: str
    is_active: bool
    last_seen_at: datetime
    enrollment_status: Optional[str] = "enrolled"
    compliance_status: Optional[str] = "compliant"
    policy_delivery_state: Optional[str] = "idle"
    capabilities: Optional[Dict[str, Any]] = None
    is_online: Optional[bool] = False
    session_id: Optional[str] = None
    batch_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

