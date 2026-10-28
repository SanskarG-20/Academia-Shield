"""
Pydantic Schemas for ML Model Training, Evaluation, and Prediction.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

class ModelTrainRequest(BaseModel):
    min_samples: int = Field(5, ge=2, description="Minimum completed session summaries required for training")
    n_estimators: int = Field(100, ge=10, le=1000)
    bootstrap_synthetic_if_insufficient: bool = Field(
        False,
        description="Opt-in parameter to synthesize realistic training samples if database lacks sufficient ground truth labels"
    )
    version_tag: Optional[str] = Field(None, max_length=50)

class ModelMetricsResponse(BaseModel):
    accuracy: float
    precision_macro: float
    recall_macro: float
    f1_macro: float
    confusion_matrix: List[List[int]]
    feature_importances: Dict[str, float]
    label_distribution: Dict[str, int]
    classes: List[str]

class MLModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_tag: str
    algorithm: str
    status: str  # draft, approved, retired
    hyperparameters_json: Optional[Dict[str, Any]] = None
    metrics_json: Optional[Dict[str, Any]] = None
    artifact_path: str
    trained_by: str
    approved_by: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None

class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_version_id: Optional[str] = None
    model_version_tag: Optional[str] = None
    student_id: str
    student_name: Optional[str] = None
    device_id: str
    batch_id: str
    session_id: str
    feature_window_id: Optional[str] = None
    prediction: str  # High, Medium, Low
    confidence: float
    probability_high: float
    probability_medium: float
    probability_low: float
    feature_snapshot_json: Optional[Dict[str, Any]] = None
    prediction_type: str  # preliminary, final
    review_status: str  # pending, reviewed
    professor_override_label: Optional[str] = None
    generated_at: datetime
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None

class PredictionReviewRequest(BaseModel):
    override_label: Optional[str] = Field(None, description="High, Medium, or Low")
    review_notes: Optional[str] = Field(None, max_length=500)

    @field_validator("override_label")
    @classmethod
    def validate_label(cls, v):
        if v is not None and v not in {"High", "Medium", "Low"}:
            raise ValueError("override_label must be one of 'High', 'Medium', 'Low'")
        return v
