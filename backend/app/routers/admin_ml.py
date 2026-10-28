"""Admin ML Model Management Router.

Endpoints:
- POST /api/v1/admin/ml/engagement/train: Train a new RandomForest engagement model on historical data.
- GET /api/v1/admin/ml/engagement/models: List all models with status, accuracy, F1, and training metadata.
- POST /api/v1/admin/ml/engagement/models/{model_id}/approve: Approve a draft model for live inference (retires old model).
- POST /api/v1/admin/ml/engagement/models/{model_id}/retire: Retire an active model.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin, require_professor
from app.models.user import User
from app.models.audit_log import AuditLog
from app.ml.schemas import (
    ModelTrainRequest,
    MLModelResponse,
)
from app.ml.train_engagement import train_engagement_model
from app.ml.model_registry import (
    list_models,
    approve_model,
    retire_model,
)

router = APIRouter(prefix="/admin/ml/engagement", tags=["Admin ML Model Management"])


@router.post("/train", response_model=MLModelResponse)
def train_model_endpoint(
    req: ModelTrainRequest,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db),
):
    """
    Train a new RandomForest model on completed sessions with professor labels.
    The resulting model is stored as 'draft' until an admin explicitly approves it.
    """
    try:
        model_version = train_engagement_model(
            db=db,
            trained_by_user_id=current_user.id,
            hyperparameters={"n_estimators": req.n_estimators},
            custom_tag=req.version_tag,
        )

        # Audit log
        audit = AuditLog(
            actor_user_id=current_user.id,
            action="TRAIN_ENGAGEMENT_MODEL",
            entity_type="ml_model",
            entity_id=model_version.id,
            metadata_json={
                "version_tag": model_version.version_tag,
                "algorithm": model_version.algorithm,
                "metrics": model_version.metrics_json,
            },
        )
        db.add(audit)
        db.commit()

        return model_version
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model training failed: {str(e)}",
        )


@router.get("/models", response_model=List[MLModelResponse])
def get_models_endpoint(
    status_filter: Optional[str] = None,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db),
):
    """List all trained model versions and their lifecycle statuses."""
    return list_models(db, status=status_filter)


@router.post("/models/{model_id}/approve", response_model=MLModelResponse)
def approve_model_endpoint(
    model_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db),
):
    """
    Approve a model for live prediction. Retires previous approved model.
    """
    try:
        model = approve_model(db, model_id=model_id, admin_user_id=current_user.id)

        audit = AuditLog(
            actor_user_id=current_user.id,
            action="APPROVE_ENGAGEMENT_MODEL",
            entity_type="ml_model",
            entity_id=model.id,
            metadata_json={"version_tag": model.version_tag},
        )
        db.add(audit)
        db.commit()

        try:
            from app.core.sockets import broadcast_engagement_model_status_changed
            broadcast_engagement_model_status_changed({
                "model_id": model.id,
                "version_tag": model.version_tag,
                "status": "approved",
                "approved_by": current_user.id,
            })
        except Exception as err:
            logger.warning(f"Failed to broadcast model approval: {err}")

        return model
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model approval failed: {str(e)}",
        )


@router.post("/models/{model_id}/retire", response_model=MLModelResponse)
def retire_model_endpoint(
    model_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db),
):
    """
    Retire a model version.
    """
    try:
        model = retire_model(db, model_id=model_id)

        audit = AuditLog(
            actor_user_id=current_user.id,
            action="RETIRE_ENGAGEMENT_MODEL",
            entity_type="ml_model",
            entity_id=model.id,
            metadata_json={"version_tag": model.version_tag},
        )
        db.add(audit)
        db.commit()

        try:
            from app.core.sockets import broadcast_engagement_model_status_changed
            broadcast_engagement_model_status_changed({
                "model_id": model.id,
                "version_tag": model.version_tag,
                "status": "retired",
            })
        except Exception as err:
            logger.warning(f"Failed to broadcast model retirement: {err}")

        return model
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model retirement failed: {str(e)}",
        )
