"""Add session_participants table and timestamps to sessions

Revision ID: 0005_add_session_participants_and_timestamps
Revises: 0004_make_session_class_id_nullable
Create Date: 2026-08-14

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0005_add_session_participants_and_timestamps"
down_revision: Union[str, None] = "0004_make_session_class_id_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    # 1. Add description, started_at, ended_at to sessions table if not present
    existing_cols = [c["name"] for c in inspector.get_columns("sessions")]
    with op.batch_alter_table("sessions") as batch_op:
        if "description" not in existing_cols:
            batch_op.add_column(sa.Column("description", sa.String(), nullable=True))
        if "started_at" not in existing_cols:
            batch_op.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        if "ended_at" not in existing_cols:
            batch_op.add_column(sa.Column("ended_at", sa.DateTime(), nullable=True))

    # 2. Create session_participants table if not present
    if "session_participants" not in tables:
        op.create_table(
            "session_participants",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("student_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="joined"),
            sa.Column("joined_at", sa.DateTime(), nullable=False),
            sa.Column("left_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "student_id", name="uq_session_student")
        )
        op.create_index("ix_session_participants_session_id", "session_participants", ["session_id"])
        op.create_index("ix_session_participants_student_id", "session_participants", ["student_id"])

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "session_participants" in tables:
        op.drop_table("session_participants")

    with op.batch_alter_table("sessions") as batch_op:
        for col in ["description", "started_at", "ended_at"]:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
