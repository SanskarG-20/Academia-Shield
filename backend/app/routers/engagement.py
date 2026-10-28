"""
Professor Live Engagement and Post-Session Labelling Router.
Provides live session engagement feature aggregations, historical PostgreSQL metrics,
batch and session selectors, and human review/override workflows.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_professor
from ..models.user import User
from ..schemas.engagement import (
    LiveEngagementResponse,
    SessionEngagementLabelCreate,
    SessionEngagementLabelResponse,
    EngagementBatchItem,
    EngagementSessionItem,
    SessionEngagementDetailResponse,
    PredictionReviewRequest,
    PredictionReviewResponse,
)
from ..services.engagement_service import EngagementService

router = APIRouter(tags=["Professor Engagement"])


# =====================================================================
# Student Engagement Dashboard APIs
# =====================================================================

@router.get("/professor/engagement/batches", response_model=List[EngagementBatchItem])
def get_professor_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Retrieve batches owned by the logged-in professor.
    Admin gets all batches.
    """
    return EngagementService.get_professor_batches(db, current_user)


@router.get("/professor/engagement/batches/{batch_id}/sessions", response_model=List[EngagementSessionItem])
def get_batch_sessions(
    batch_id: str,
    status: Optional[str] = Query(None, description="Status filter: Active, Completed, All"),
    start_date: Optional[str] = Query(None, description="Optional start date ISO filter"),
    end_date: Optional[str] = Query(None, description="Optional end date ISO filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Retrieve sessions belonging to the selected batch.
    Enforces server-side batch ownership check.
    """
    return EngagementService.get_batch_sessions(
        db=db,
        batch_id=batch_id,
        status_filter=status,
        start_date=start_date,
        end_date=end_date,
        current_user=current_user,
    )


@router.get("/professor/engagement/sessions/{session_id}", response_model=SessionEngagementDetailResponse)
def get_session_engagement(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Retrieve student engagement data for a specific session.
    Live sessions return real-time aggregated telemetry and preliminary predictions.
    Completed sessions return saved PostgreSQL summaries and final predictions.
    Enforces server-side ownership.
    """
    return EngagementService.get_session_engagement_detail(db, session_id, current_user)


@router.get("/professor/engagement/sessions/{session_id}/history")
def get_session_engagement_history(
    session_id: str,
    student_id: Optional[str] = Query(None, description="Optional student ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Retrieve historical engagement predictions for students across this session.
    """
    return EngagementService.get_session_prediction_history(db, session_id, current_user, student_id=student_id)


@router.patch("/professor/engagement/predictions/{prediction_id}/review", response_model=PredictionReviewResponse)
def review_engagement_prediction(
    prediction_id: str,
    review_data: PredictionReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Review and optionally override an advisory engagement prediction.
    Preserves immutable model output and records an audit log.
    """
    return EngagementService.review_prediction_with_audit(db, prediction_id, review_data, current_user)


# =====================================================================
# Legacy / Compatibility Endpoints
# =====================================================================

@router.get("/professor/sessions/{session_id}/engagement/live", response_model=LiveEngagementResponse)
def get_live_session_engagement(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """Legacy live telemetry aggregation endpoint."""
    return EngagementService.get_live_session_engagement(db, session_id, current_user)


@router.post("/professor/sessions/{session_id}/engagement/label", response_model=SessionEngagementLabelResponse)
def create_or_update_session_label(
    session_id: str,
    label_data: SessionEngagementLabelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """Submit post-session human ground truth label."""
    return EngagementService.create_or_update_session_label(db, session_id, label_data, current_user)


@router.get("/professor/sessions/{session_id}/engagement/labels", response_model=List[SessionEngagementLabelResponse])
def get_session_labels(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """Fetch post-session human ground truth labels."""
    return EngagementService.get_session_labels(db, session_id, current_user)


@router.get("/professor/sessions/{session_id}/engagement/history")
def get_legacy_session_engagement_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """Legacy session history endpoint."""
    return EngagementService.get_session_prediction_history(db, session_id, current_user)


@router.patch("/professor/sessions/engagement-predictions/{prediction_id}/review")
def review_legacy_engagement_prediction(
    prediction_id: str,
    override_label: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """Legacy prediction review endpoint."""
    return EngagementService.review_prediction(db, prediction_id, override_label, current_user)
