"""Add Application Rules extension and Protected Processes table

Revision ID: 0002_add_application_rules_and_protected_processes
Revises: 0001_initial_schema
Create Date: 2026-08-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0002_add_application_rules_and_protected_processes"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_PROTECTED_PROCESSES = [
    {"executable_name": "explorer.exe", "description": "Windows shell process"},
    {"executable_name": "svchost.exe", "description": "Windows Host Process for Services"},
    {"executable_name": "csrss.exe", "description": "Client Server Runtime Process"},
    {"executable_name": "smss.exe", "description": "Windows Session Manager"},
    {"executable_name": "services.exe", "description": "Services Control Manager"},
    {"executable_name": "lsass.exe", "description": "Local Security Authority Subsystem Service"},
    {"executable_name": "winlogon.exe", "description": "Windows Logon Process"},
    {"executable_name": "systemd", "description": "Linux system initialization process"},
    {"executable_name": "python.exe", "description": "Python interpreter / Agent core runtime"},
    {"executable_name": "python", "description": "Python interpreter / Agent core runtime"},
    {"executable_name": "academia_shield_agent.exe", "description": "Academia Shield Local Agent service"}
]

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # 1. Create protected_processes table if not existing
    if "protected_processes" not in inspector.get_table_names():
        op.create_table(
            "protected_processes",
            sa.Column("id", sa.String(), nullable=False, primary_key=True),
            sa.Column("executable_name", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("executable_path_pattern", sa.String(), nullable=True),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

        # Seed initial default protected processes
        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        protected_table = sa.table(
            "protected_processes",
            sa.column("id", sa.String),
            sa.column("executable_name", sa.String),
            sa.column("description", sa.String),
            sa.column("is_enabled", sa.Boolean),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime)
        )
        op.bulk_insert(
            protected_table,
            [
                {
                    "id": str(uuid.uuid4()),
                    "executable_name": item["executable_name"],
                    "description": item["description"],
                    "is_enabled": True,
                    "created_at": now,
                    "updated_at": now,
                }
                for item in DEFAULT_PROTECTED_PROCESSES
            ]
        )

    # 2. Ensure application_rules table has all columns
    if "application_rules" in inspector.get_table_names():
        app_columns = [col["name"] for col in inspector.get_columns("application_rules")]
        if "trusted_hash" not in app_columns:
            op.add_column("application_rules", sa.Column("trusted_hash", sa.String(length=64), nullable=True))
        if "reason" not in app_columns:
            op.add_column("application_rules", sa.Column("reason", sa.String(), nullable=True))
        if "cooldown_seconds" not in app_columns:
            op.add_column("application_rules", sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="0"))
        if "created_at" not in app_columns:
            op.add_column("application_rules", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        if "updated_at" not in app_columns:
            op.add_column("application_rules", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    if "protected_processes" in inspector.get_table_names():
        op.drop_table("protected_processes")

    if "application_rules" in inspector.get_table_names():
        app_columns = [col["name"] for col in inspector.get_columns("application_rules")]
        if "trusted_hash" in app_columns:
            op.drop_column("application_rules", "trusted_hash")
        if "reason" in app_columns:
            op.drop_column("application_rules", "reason")
        if "cooldown_seconds" in app_columns:
            op.drop_column("application_rules", "cooldown_seconds")
        if "created_at" in app_columns:
            op.drop_column("application_rules", "created_at")
        if "updated_at" in app_columns:
            op.drop_column("application_rules", "updated_at")
