from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from .rule import DomainRuleResponse, ApplicationRuleResponse, ProtectedProcessResponse

class DeviceRegisterRequest(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=100)
    device_identifier: str = Field(..., min_length=1, max_length=100)
    public_key: str = Field(..., min_length=16)  # Ed25519 public key hex/string
    platform: str = Field(..., min_length=1, max_length=50)  # windows, macos, linux
    platform_version: Optional[str] = None
    agent_version: str = Field(..., min_length=1, max_length=20)
    capabilities: Optional[Dict[str, Any]] = None

class DeviceRegisterResponse(BaseModel):
    device_id: str
    user_id: str
    device_identifier: str
    enrolled_at: datetime
    status: str = "registered"
    enrollment_status: str = "enrolled"

class DeviceEnrollRequest(BaseModel):
    enrollment_token: Optional[str] = None
    device_id: Optional[str] = None
    device_name: Optional[str] = "Student Endpoint"
    device_identifier: Optional[str] = None
    public_key: Optional[str] = None  # Ed25519 public key
    platform: Optional[str] = "windows"
    platform_version: Optional[str] = None
    agent_version: Optional[str] = "2.3.0"
    capabilities: Optional[Dict[str, Any]] = None


class EnrollmentTokenResponse(BaseModel):
    enrollment_token: str
    expires_at: datetime
    student_name: str
    student_id: str
    instructions: str = "Enter this one-time code into the Academia Shield Desktop Agent to enroll this device."


class DeviceEnrollResponse(BaseModel):
    device_id: str
    user_id: str
    device_identifier: str
    enrolled_at: datetime
    status: str = "enrolled"
    enrollment_status: str = "enrolled"
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class HeartbeatRequest(BaseModel):
    model_config = {"extra": "allow"}

    device_id: Optional[str] = None
    device_identifier: Optional[str] = None
    platform: Optional[str] = None
    agent_version: str = Field(..., min_length=1, max_length=50)
    agent_installed: bool = True
    agent_service_running: bool = False
    current_session_id: Optional[str] = None
    scheduler_status: Optional[str] = "active"
    policy_version: Optional[int] = None
    last_time_sync_at: Optional[datetime] = None
    
    # Capability Statuses
    dns_enforcement: Optional[str] = None  # active, unavailable, requires_approval
    dns_enforcement_status: Optional[str] = None
    dns_status: Optional[str] = "normal"
    content_filter: Optional[str] = None   # active, unavailable, requires_mdm
    application_control: Optional[str] = None  # active, unavailable, requires_mdm
    application_control_status: Optional[str] = None
    application_monitor_status: Optional[str] = "active"
    browser_policy: Optional[str] = None   # active, unavailable, requires_mdm
    usb_storage_policy: Optional[str] = None # active, unavailable, requires_mdm
    usb_storage_restricted: bool = False
    usb_storage_restriction_status: Optional[str] = None # active, inactive, unsupported, requires_managed_device, error
    device_compliance: Optional[str] = "compliant" # compliant, non_compliant, unknown

    health_state: Optional[str] = "healthy"
    health_status: Optional[str] = None
    active_session_state: Optional[str] = "active"
    active_policy_version: Optional[int] = None
    current_policy_version: Optional[int] = None
    last_scan_timestamp: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    error_code: Optional[str] = None

class ActivePolicyResponse(BaseModel):
    policy_active: bool
    policy_id: Optional[str] = None
    policy_version: Optional[int] = None
    student_id: Optional[str] = None
    device_id: Optional[str] = None
    batch_id: Optional[str] = None
    session_id: Optional[str] = None
    target_platform: Optional[str] = None
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    integrity_hash: Optional[str] = None
    signature: Optional[str] = None
    canonical_payload: Optional[str] = None
    enforcement_mode: Optional[str] = "development" # audit, development, managed
    required_capabilities: List[str] = []
    reason: Optional[str] = None

    # Structured rules and device requirements
    allowed_websites: List[Union[str, Dict[str, Any]]] = []
    blocked_websites: List[Union[str, Dict[str, Any]]] = []
    allowed_applications: List[Union[str, Dict[str, Any]]] = []
    blocked_applications: List[Union[str, Dict[str, Any]]] = []
    device_requirements: Dict[str, Any] = {}

    # Scheduling & Temporal info
    session_status: Optional[str] = None
    timezone: Optional[str] = "UTC"
    start_at_utc: Optional[datetime] = None
    end_at_utc: Optional[datetime] = None
    recurrence_type: Optional[str] = "none"
    recurrence_interval: Optional[int] = 1
    recurrence_days_of_week: Optional[List[Any]] = None
    recurrence_until_utc: Optional[datetime] = None
    server_time_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    max_allowed_clock_skew_seconds: int = 120
    upstream_dns: List[str] = ["8.8.8.8", "1.1.1.1"]
    
    # Rules
    domains: List[str] = []
    apps: List[Dict[str, Any]] = []
    domain_rules: List[DomainRuleResponse] = []
    application_rules: List[ApplicationRuleResponse] = []
    protected_processes: List[ProtectedProcessResponse] = []
    enforcement_settings: Dict[str, Any] = {
        "poll_interval": 8,
        "dns_port": 5353,
        "allow_fallback": True
    }

class PolicyAcknowledgeRequest(BaseModel):
    policy_id: Optional[str] = None
    status: str = Field(..., description="delivered, acknowledged, active, restored, rejected")
    error_message: Optional[str] = None
    active_capabilities: Optional[List[str]] = None
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

class PolicyAcknowledgeResponse(BaseModel):
    success: bool
    policy_id: str
    status: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TelemetryEventItem(BaseModel):
    model_config = {"extra": "allow"}

    event_id: Optional[str] = None  # Unique UUID idempotency key
    event_type: Optional[str] = "heartbeat"
    device_id: Optional[str] = None
    device_identifier: Optional[str] = None
    session_id: Optional[str] = None
    policy_version: Optional[int] = None
    rule_id: Optional[str] = None
    executable_name: Optional[str] = None
    action_requested: Optional[str] = None
    action_result: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    occurred_at: Optional[datetime] = None


class ReleaseManifestResponse(BaseModel):
    platform: str
    version: str
    download_url: str
    sha256: str
    release_date: str
    signature: str
    min_os_version: str


class ReleaseListResponse(BaseModel):
    latest_version: str
    releases: Dict[str, ReleaseManifestResponse]


class VerificationKeyResponse(BaseModel):
    public_key: str
    algorithm: str = "Ed25519"
    key_type: str = "Asymmetric"
    issuer: str = "Academia Shield Security Authority"


class DeviceRevokeResponse(BaseModel):
    device_id: str
    enrollment_status: str = "revoked"
    is_active: bool = False
    revoked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str = "Device has been successfully revoked"


