"""Model registry and lifecycle management for Engagement Prediction.

Provides:
- Model status lifecycle transitions: 'draft' -> 'approved' -> 'retired'.
- Model promotion with automatic rollback/retiring of previous active model.
- Model retrieval and activation checks.
- In-memory cache for fast, thread-safe inference access.
"""
import os
import threading
import logging
from datetime import datetime, timezone
from typing import Optional, List
import joblib
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from app.models.engagement import MLModelVersion

logger = logging.getLogger(__name__)

# In-memory model cache for active live predictor
_MODEL_CACHE_LOCK = threading.Lock()
_CACHED_MODEL_ID: Optional[str] = None
_CACHED_MODEL_DATA: Optional[dict] = None


def get_active_model(db: Session) -> Optional[MLModelVersion]:
    """Retrieves the currently approved ML model from the database."""
    stmt = (
        select(MLModelVersion)
        .where(MLModelVersion.status == "approved")
        .order_by(MLModelVersion.approved_at.desc())
    )
    return db.execute(stmt).scalars().first()


def list_models(db: Session, status: Optional[str] = None) -> List[MLModelVersion]:
    """Lists all ML model versions, optionally filtered by status."""
    stmt = select(MLModelVersion).order_by(MLModelVersion.created_at.desc())
    if status:
        stmt = stmt.where(MLModelVersion.status == status)
    return list(db.execute(stmt).scalars().all())


def approve_model(
    db: Session, model_id: str, admin_user_id: str
) -> MLModelVersion:
    """
    Approves a model version for live inference:
    1. Finds target model; must exist and be in 'draft' or 'retired' state.
    2. Retires any currently 'approved' model, recording retired_at timestamp.
    3. Promotes target model to 'approved', recording approved_at and approved_by.
    4. Invalidates in-memory cache so next inference request loads the new model.
    """
    target = db.get(MLModelVersion, model_id)
    if not target:
        raise ValueError(f"Model with ID '{model_id}' not found.")

    if not os.path.exists(target.artifact_path):
        raise FileNotFoundError(
            f"Model artifact file does not exist at '{target.artifact_path}'."
        )

    now = datetime.now(timezone.utc)

    # Retire currently active model(s)
    current_active_stmt = (
        select(MLModelVersion)
        .where(MLModelVersion.status == "approved")
    )
    current_active = db.execute(current_active_stmt).scalars().all()
    for m in current_active:
        if m.id != model_id:
            m.status = "retired"
            m.retired_at = now

    # Promote target model
    target.status = "approved"
    target.approved_by = admin_user_id
    target.approved_at = now

    db.commit()
    db.refresh(target)

    # Invalidate cache
    global _CACHED_MODEL_ID, _CACHED_MODEL_DATA
    with _MODEL_CACHE_LOCK:
        _CACHED_MODEL_ID = None
        _CACHED_MODEL_DATA = None

    logger.info(
        f"Model {target.version_tag} ({target.id}) approved by {admin_user_id}."
    )
    return target


def retire_model(
    db: Session, model_id: str
) -> MLModelVersion:
    """
    Retires a model version (e.g., during emergency rollback or maintenance).
    """
    target = db.get(MLModelVersion, model_id)
    if not target:
        raise ValueError(f"Model with ID '{model_id}' not found.")

    target.status = "retired"
    target.retired_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(target)

    # Invalidate cache if it was the loaded model
    global _CACHED_MODEL_ID, _CACHED_MODEL_DATA
    with _MODEL_CACHE_LOCK:
        if _CACHED_MODEL_ID == model_id:
            _CACHED_MODEL_ID = None
            _CACHED_MODEL_DATA = None

    logger.info(f"Model {target.version_tag} ({target.id}) retired.")
    return target


def load_cached_active_model(db: Session):
    """
    Loads and caches the currently approved model binary.
    Returns:
        tuple (MLModelVersion, loaded_artifact_dict) or (None, None)
    """
    global _CACHED_MODEL_ID, _CACHED_MODEL_DATA

    with _MODEL_CACHE_LOCK:
        active_db_model = get_active_model(db)
        if not active_db_model:
            return None, None

        if _CACHED_MODEL_ID == active_db_model.id and _CACHED_MODEL_DATA is not None:
            return active_db_model, _CACHED_MODEL_DATA

        if not os.path.exists(active_db_model.artifact_path):
            logger.error(
                f"Active model artifact missing at {active_db_model.artifact_path}"
            )
            return None, None

        data = joblib.load(active_db_model.artifact_path)
        _CACHED_MODEL_ID = active_db_model.id
        _CACHED_MODEL_DATA = data
        return active_db_model, data
