"""Add engagement_feature_windows and session_engagement_labels tables

Revision ID: 0007_add_engagement_feature_windows
Revises: 0006_add_session_presence
Create Date: 2026-09-05

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0007_add_engagement_feature_windows"
down_revision: Union[str, None] = "0006_add_session_presence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "engagement_feature_windows" not in tables:
        op.create_table(
            "engagement_feature_windows",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("event_id", sa.String(), nullable=False),
            sa.Column("student_id", sa.String(), nullable=False),
            sa.Column("device_id", sa.String(), nullable=False),
            sa.Column("batch_id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("window_start_at", sa.DateTime(), nullable=False),
            sa.Column("window_end_at", sa.DateTime(), nullable=False),
            sa.Column("policy_version", sa.Integer(), nullable=False),
            sa.Column("academic_active_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("non_academic_active_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("idle_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("application_switch_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unauthorized_application_attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("blocked_website_attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("policy_violation_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("session_elapsed_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("validation_status", sa.String(), nullable=False, server_default="valid"),
            sa.Column("validation_error", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["device_id"], ["agent_devices.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", name="uq_engagement_feature_windows_event_id")
        )
        op.create_index("ix_engagement_feature_windows_event_id", "engagement_feature_windows", ["event_id"])
        op.create_index("ix_engagement_feature_windows_student_id", "engagement_feature_windows", ["student_id"])
        op.create_index("ix_engagement_feature_windows_device_id", "engagement_feature_windows", ["device_id"])
        op.create_index("ix_engagement_feature_windows_batch_id", "engagement_feature_windows", ["batch_id"])
        op.create_index("ix_engagement_feature_windows_session_id", "engagement_feature_windows", ["session_id"])
        op.create_index("ix_engagement_feature_windows_validation_status", "engagement_feature_windows", ["validation_status"])
    else:
        columns = [c["name"] for c in inspector.get_columns("engagement_feature_windows")]
        if "event_id" not in columns:
            op.add_column("engagement_feature_windows", sa.Column("event_id", sa.String(), nullable=True))
            op.create_index("ix_engagement_feature_windows_event_id", "engagement_feature_windows", ["event_id"])
        if "policy_version" not in columns:
            op.add_column("engagement_feature_windows", sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"))
        if "validation_status" not in columns:
            op.add_column("engagement_feature_windows", sa.Column("validation_status", sa.String(), nullable=False, server_default="valid"))
            op.create_index("ix_engagement_feature_windows_validation_status", "engagement_feature_windows", ["validation_status"])
        if "validation_error" not in columns:
            op.add_column("engagement_feature_windows", sa.Column("validation_error", sa.String(), nullable=True))

    if "session_engagement_labels" not in tables:
        op.create_table(
            "session_engagement_labels",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("student_id", sa.String(), nullable=False),
            sa.Column("professor_id", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["professor_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "student_id", name="uq_session_student_engagement_label")
        )
        op.create_index("ix_session_engagement_labels_session_id", "session_engagement_labels", ["session_id"])
        op.create_index("ix_session_engagement_labels_student_id", "session_engagement_labels", ["student_id"])
        op.create_index("ix_session_engagement_labels_professor_id", "session_engagement_labels", ["professor_id"])

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "session_engagement_labels" in tables:
        op.drop_table("session_engagement_labels")

    if "engagement_feature_windows" in tables:
        op.drop_table("engagement_feature_windows")
