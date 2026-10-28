"""Extend sessions schema and create audit_logs table

Revision ID: 0003_extend_sessions_and_add_audit_logs
Revises: 0002_add_application_rules_and_protected_processes
Create Date: 2026-08-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0003_extend_sessions_and_add_audit_logs"
down_revision: Union[str, None] = "0002_add_application_rules_and_protected_processes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # 1. Extend sessions table
    existing_cols = [c["name"] for c in inspector.get_columns("sessions")]

    if "start_at_utc" not in existing_cols:
        op.add_column("sessions", sa.Column("start_at_utc", sa.DateTime(), nullable=True))
        # Populate from start_at
        conn.execute(sa.text("UPDATE sessions SET start_at_utc = start_at WHERE start_at_utc IS NULL"))
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.alter_column("start_at_utc", nullable=False)

    if "end_at_utc" not in existing_cols:
        op.add_column("sessions", sa.Column("end_at_utc", sa.DateTime(), nullable=True))
        conn.execute(sa.text("UPDATE sessions SET end_at_utc = end_at WHERE end_at_utc IS NULL"))
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.alter_column("end_at_utc", nullable=False)

    if "recurrence_type" not in existing_cols:
        op.add_column("sessions", sa.Column("recurrence_type", sa.String(), nullable=False, server_default="none"))

    if "recurrence_interval" not in existing_cols:
        op.add_column("sessions", sa.Column("recurrence_interval", sa.Integer(), nullable=False, server_default="1"))

    if "recurrence_days_of_week" not in existing_cols:
        op.add_column("sessions", sa.Column("recurrence_days_of_week", sa.JSON(), nullable=True))

    if "recurrence_until_utc" not in existing_cols:
        op.add_column("sessions", sa.Column("recurrence_until_utc", sa.DateTime(), nullable=True))

    if "policy_version" not in existing_cols:
        op.add_column("sessions", sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"))

    if "updated_at" not in existing_cols:
        op.add_column("sessions", sa.Column("updated_at", sa.DateTime(), nullable=True))
        conn.execute(sa.text("UPDATE sessions SET updated_at = created_at WHERE updated_at IS NULL"))
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.alter_column("updated_at", nullable=False)

    # Normalize status values: Upcoming -> scheduled, Completed -> ended
    conn.execute(sa.text("UPDATE sessions SET status = 'scheduled' WHERE status = 'Upcoming'"))
    conn.execute(sa.text("UPDATE sessions SET status = 'ended' WHERE status = 'Completed'"))

    # 2. Create audit_logs table if not existing
    tables = inspector.get_table_names()
    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("actor_user_id", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("entity_type", sa.String(), nullable=False),
            sa.Column("entity_id", sa.String(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id")
        )
        op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
        op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "audit_logs" in tables:
        op.drop_table("audit_logs")

    with op.batch_alter_table("sessions") as batch_op:
        for col in ["start_at_utc", "end_at_utc", "recurrence_type", "recurrence_interval", "recurrence_days_of_week", "recurrence_until_utc", "policy_version", "updated_at"]:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
