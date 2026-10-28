"""Add engagement_session_summaries table

Revision ID: 0009_add_engagement_session_summaries
Revises: 0008_add_ml_models_and_predictions
Create Date: 2026-09-06

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0009_add_engagement_session_summaries"
down_revision: Union[str, None] = "0008_add_engagement_ml_models_and_predictions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "engagement_session_summaries" not in tables:
        op.create_table(
            "engagement_session_summaries",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("student_id", sa.String(), nullable=False),
            sa.Column("batch_id", sa.String(), nullable=False),
            sa.Column("device_id", sa.String(), nullable=True),
            sa.Column("academic_active_seconds", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("non_academic_active_seconds", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("idle_seconds", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("application_switch_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unauthorized_application_attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("blocked_website_attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("policy_violation_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("session_elapsed_seconds", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("final_prediction_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["device_id"], ["agent_devices.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["final_prediction_id"], ["engagement_predictions.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "student_id", name="uq_session_student_engagement_summary")
        )
        op.create_index("ix_engagement_session_summaries_session_id", "engagement_session_summaries", ["session_id"])
        op.create_index("ix_engagement_session_summaries_student_id", "engagement_session_summaries", ["student_id"])
        op.create_index("ix_engagement_session_summaries_batch_id", "engagement_session_summaries", ["batch_id"])

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "engagement_session_summaries" in tables:
        op.drop_table("engagement_session_summaries")
