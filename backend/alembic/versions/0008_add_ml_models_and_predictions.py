"""Add ml_models and engagement_predictions tables

Revision ID: 0008_add_ml_models_and_predictions
Revises: 0007_add_engagement_feature_windows
Create Date: 2026-09-05

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0008_add_engagement_ml_models_and_predictions"
down_revision: Union[str, None] = "0007_add_engagement_feature_windows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "ml_models" not in tables:
        op.create_table(
            "ml_models",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("version_tag", sa.String(), nullable=False),
            sa.Column("algorithm", sa.String(), nullable=False, server_default="RandomForestClassifier"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("hyperparameters_json", sa.JSON(), nullable=True),
            sa.Column("metrics_json", sa.JSON(), nullable=True),
            sa.Column("artifact_path", sa.String(), nullable=False),
            sa.Column("trained_by", sa.String(), nullable=False),
            sa.Column("approved_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("retired_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["trained_by"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("version_tag", name="uq_ml_models_version_tag")
        )
        op.create_index("ix_ml_models_version_tag", "ml_models", ["version_tag"])
        op.create_index("ix_ml_models_status", "ml_models", ["status"])

    if "engagement_predictions" not in tables:
        op.create_table(
            "engagement_predictions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("model_version_id", sa.String(), nullable=True),
            sa.Column("student_id", sa.String(), nullable=False),
            sa.Column("device_id", sa.String(), nullable=False),
            sa.Column("batch_id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("feature_window_id", sa.String(), nullable=True),
            sa.Column("prediction", sa.String(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("probability_high", sa.Float(), nullable=False),
            sa.Column("probability_medium", sa.Float(), nullable=False),
            sa.Column("probability_low", sa.Float(), nullable=False),
            sa.Column("feature_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("prediction_type", sa.String(), nullable=False, server_default="preliminary"),
            sa.Column("review_status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("professor_override_label", sa.String(), nullable=True),
            sa.Column("generated_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_by", sa.String(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["model_version_id"], ["ml_models.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["device_id"], ["agent_devices.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["feature_window_id"], ["engagement_feature_windows.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("model_version_id", "feature_window_id", name="uq_model_feature_window_prediction")
        )
        op.create_index("ix_engagement_predictions_student_id", "engagement_predictions", ["student_id"])
        op.create_index("ix_engagement_predictions_device_id", "engagement_predictions", ["device_id"])
        op.create_index("ix_engagement_predictions_batch_id", "engagement_predictions", ["batch_id"])
        op.create_index("ix_engagement_predictions_session_id", "engagement_predictions", ["session_id"])
        op.create_index("ix_engagement_predictions_feature_window_id", "engagement_predictions", ["feature_window_id"])
        op.create_index("ix_engagement_predictions_model_version_id", "engagement_predictions", ["model_version_id"])

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "engagement_predictions" in tables:
        op.drop_table("engagement_predictions")

    if "ml_models" in tables:
        op.drop_table("ml_models")
