"""
Pydantic Schemas for Engagement Feature Windows and Labelling.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

class EngagementFeatureWindowCreate(BaseModel):
    event_id: str = Field(..., min_length=1, description="Unique client event UUID for idempotency")
    student_id: str = Field(..., min_length=1)
    device_id: str = Field(..., min_length=1)
    batch_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    window_start_at: Optional[datetime] = None
    window_end_at: Optional[datetime] = None
    window_started_at: Optional[datetime] = None
    window_ended_at: Optional[datetime] = None
    policy_version: int = Field(1, ge=1)

    # Privacy-minimized aggregated telemetry features
    allowed_academic_application_active_seconds: float = Field(0.0, ge=0.0)
    allowed_academic_website_active_seconds: float = Field(0.0, ge=0.0)
    allowed_academic_active_seconds: float = Field(0.0, ge=0.0)
    academic_active_seconds: float = Field(0.0, ge=0.0)
    non_academic_active_seconds: float = Field(0.0, ge=0.0)
    idle_seconds: float = Field(0.0, ge=0.0)
    unknown_or_unavailable_seconds: float = Field(0.0, ge=0.0)
    active_resource_sample_count: int = Field(0, ge=0)
    unknown_resource_sample_count: int = Field(0, ge=0)
    application_switch_count: int = Field(0, ge=0)
    unauthorized_application_attempt_count: int = Field(0, ge=0)
    blocked_website_attempt_count: int = Field(0, ge=0)
    policy_violation_count: int = Field(0, ge=0)
    session_elapsed_seconds: float = Field(0.0, ge=0.0)
    feature_completeness_percent: float = Field(100.0, ge=0.0, le=100.0)
    completeness_percent: float = Field(100.0, ge=0.0, le=100.0)
    approved_resources_breakdown: Optional[dict] = None
    approved_apps_breakdown: Optional[dict] = None
    approved_websites_breakdown: Optional[dict] = None

    @model_validator(mode="after")
    def validate_durations_and_times(self):
        start = self.window_start_at or self.window_started_at
        end = self.window_end_at or self.window_ended_at
        if not start or not end:
            raise ValueError("window_start_at (or window_started_at) and window_end_at (or window_ended_at) are required")
        if end <= start:
            raise ValueError("window_end_at must be strictly greater than window_start_at")
        self.window_start_at = start
        self.window_end_at = end

        # Reconcile academic active seconds
        if self.allowed_academic_active_seconds == 0.0 and (self.allowed_academic_application_active_seconds > 0 or self.allowed_academic_website_active_seconds > 0):
            self.allowed_academic_active_seconds = self.allowed_academic_application_active_seconds + self.allowed_academic_website_active_seconds
        if self.academic_active_seconds == 0.0:
            self.academic_active_seconds = self.allowed_academic_active_seconds

        win_duration = (end - start).total_seconds()
        total_classified = (
            self.allowed_academic_active_seconds +
            self.non_academic_active_seconds +
            self.idle_seconds +
            self.unknown_or_unavailable_seconds
        )
        # Classifications must sum to window duration within reasonable tolerance
        if total_classified > 0 and win_duration > 5.0 and abs(total_classified - win_duration) > 10.0:
            raise ValueError(
                f"Classification totals ({total_classified:.1f}s) must sum to the window duration ({win_duration:.1f}s)"
            )
        return self

# Type alias for compatibility
EngagementWindowPayload = EngagementFeatureWindowCreate

class EngagementFeatureWindowResponse(BaseModel):
    id: Optional[str] = None
    event_id: str
    status: str  # "accepted", "duplicate", "invalid", "rejected"
    message: Optional[str] = None

class LiveEngagementStudentItem(BaseModel):
    student_id: str
    student_name: str
    student_email: str
    batch_id: str
    joined: bool
    last_window_at: Optional[datetime] = None
    window_count: int = 0
    allowed_academic_application_active_seconds: float = 0.0
    allowed_academic_website_active_seconds: float = 0.0
    allowed_academic_active_seconds: float = 0.0
    total_academic_seconds: float = 0.0
    total_non_academic_seconds: float = 0.0
    total_idle_seconds: float = 0.0
    unknown_or_unavailable_seconds: float = 0.0
    total_switches: int = 0
    total_unauthorized_attempts: int = 0
    total_blocked_website_attempts: int = 0
    total_policy_violations: int = 0
    academic_ratio: float = 0.0
    allowed_app_ratio: float = 0.0
    allowed_website_ratio: float = 0.0
    idle_ratio: float = 0.0
    focus_stability_index: float = 1.0
    violation_rate_per_hour: float = 0.0
    feature_completeness_percent: float = 100.0
    approved_apps_summary: Optional[dict] = None
    approved_websites_summary: Optional[dict] = None
    collection_status: Optional[str] = "collecting"
    label: Optional[str] = None
    prediction_available: bool = False
    prediction_reason: Optional[str] = None
    predicted_engagement: Optional[str] = None  # High, Medium, Low
    confidence: Optional[float] = None
    probability_high: Optional[float] = None
    probability_medium: Optional[float] = None
    probability_low: Optional[float] = None
    model_version: Optional[str] = None
    prediction_type: Optional[str] = None  # live, final
    review_status: Optional[str] = None  # preliminary, reviewed
    latest_prediction_id: Optional[str] = None
    professor_override_label: Optional[str] = None

class LiveEngagementResponse(BaseModel):
    session_id: str
    session_title: str
    session_status: str
    is_active: bool
    prediction_available: bool = False
    students: List[LiveEngagementStudentItem]

class SessionEngagementLabelCreate(BaseModel):
    student_id: str = Field(..., min_length=1)
    label: str = Field(..., description="High, Medium, or Low")
    notes: Optional[str] = None

    @field_validator("label")
    @classmethod
    def validate_label_value(cls, v: str):
        allowed = {"High", "Medium", "Low"}
        if v not in allowed:
            raise ValueError(f"Label must be one of {allowed}")
        return v

class SessionEngagementLabelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    student_id: str
    professor_id: str
    label: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EngagementBatchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    student_count: int = 0
    created_at: Optional[datetime] = None


class EngagementSessionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_id: str
    title: str
    status: str
    is_active: bool
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    participant_count: int = 0


class StudentEngagementRowItem(BaseModel):
    student_name: str
    student_id: str
    student_email: Optional[str] = None
    session_status: str  # "Joined", "Left", "Offline"
    policy_status: str   # "Active", "Restored", "Failed"
    allowed_academic_application_active_seconds: float = 0.0
    allowed_academic_website_active_seconds: float = 0.0
    allowed_academic_active_seconds: float = 0.0
    academic_activity_seconds: float = 0.0
    non_academic_activity_seconds: float = 0.0
    idle_seconds: float = 0.0
    unknown_or_unavailable_seconds: float = 0.0
    feature_completeness_percent: float = 100.0
    approved_apps_summary: Optional[dict] = None
    approved_websites_summary: Optional[dict] = None
    application_switch_count: int = 0
    blocked_website_attempt_count: int = 0
    unauthorized_application_attempt_count: int = 0
    policy_violation_count: int = 0
    engagement_estimate: Optional[str] = None  # "High", "Medium", "Low"
    confidence: Optional[float] = None
    probability_high: Optional[float] = None
    probability_medium: Optional[float] = None
    probability_low: Optional[float] = None
    collection_status: Optional[str] = "collecting"  # "collecting", "data_insufficient", "preliminary_prediction", "final_prediction"
    valid_windows_received: int = 0
    minimum_windows_required: int = 1
    session_elapsed_seconds: float = 0.0
    last_telemetry_at: Optional[datetime] = None
    prediction_type: Optional[str] = None  # "Collecting", "Live Preliminary", or "Final"
    prediction_available: bool = False
    prediction_reason: Optional[str] = None
    last_updated_time: Optional[datetime] = None
    professor_review_status: Optional[str] = None  # "pending", "confirmed", "overridden", "reviewed"
    professor_override_label: Optional[str] = None  # "High", "Medium", "Low"
    prediction_id: Optional[str] = None
    model_version: Optional[str] = None
    is_advisory: bool = True
    review_required: bool = True


class SessionEngagementDetailResponse(BaseModel):
    session_id: str
    session_title: str
    batch_id: str
    batch_name: str
    session_status: str
    is_active: bool
    has_active_model: bool = True
    model_version_tag: Optional[str] = None
    students: List[StudentEngagementRowItem] = []
    empty_reason: Optional[str] = None


class PredictionReviewRequest(BaseModel):
    action: str = Field("confirm", description="'confirm' or 'override'")
    override_label: Optional[str] = Field(None, description="'High', 'Medium', or 'Low'")
    notes: Optional[str] = None

    @field_validator("override_label")
    @classmethod
    def validate_override_label(cls, v: Optional[str], info):
        if v is not None:
            allowed = {"High", "Medium", "Low"}
            if v not in allowed:
                raise ValueError(f"override_label must be one of {allowed}")
        return v


class PredictionReviewResponse(BaseModel):
    prediction_id: str
    session_id: str
    student_id: str
    model_estimate: str
    confidence: float
    professor_review_status: str
    professor_override_label: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    message: str
