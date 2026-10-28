"""Add session_presence table

Revision ID: 0006_add_session_presence
Revises: 0005_add_session_participants_and_timestamps
Create Date: 2026-08-14

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0006_add_session_presence"
down_revision: Union[str, None] = "0005_add_session_participants_and_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "session_presence" not in tables:
        op.create_table(
            "session_presence",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("student_id", sa.String(), nullable=False),
            sa.Column("browser_last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("agent_last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("connected_socket_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("joined_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "student_id", name="uq_session_presence_student")
        )
        op.create_index("ix_session_presence_session_id", "session_presence", ["session_id"])
        op.create_index("ix_session_presence_student_id", "session_presence", ["student_id"])

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "session_presence" in tables:
        op.drop_table("session_presence")
