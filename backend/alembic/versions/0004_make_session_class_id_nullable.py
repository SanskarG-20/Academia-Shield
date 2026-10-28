"""Make sessions class_id, start_at, and end_at columns nullable

Revision ID: 0004_make_session_class_id_nullable
Revises: 0003_extend_sessions_and_add_audit_logs
Create Date: 2026-08-14

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_make_session_class_id_nullable"
down_revision: Union[str, None] = "0003_extend_sessions_and_add_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("class_id", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("start_at", existing_type=sa.DateTime(), nullable=True)
        batch_op.alter_column("end_at", existing_type=sa.DateTime(), nullable=True)

def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("class_id", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("start_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column("end_at", existing_type=sa.DateTime(), nullable=False)
