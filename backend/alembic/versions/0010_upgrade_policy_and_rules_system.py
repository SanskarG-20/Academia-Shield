"""Upgrade policy and rules system with website_rules, device_policy_requirements, and extended rule_set / application_rules

Revision ID: 0010_upgrade_policy_and_rules_system
Revises: 0009_add_engagement_session_summaries
Create Date: 2026-09-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0010_upgrade_policy_and_rules_system"
down_revision: Union[str, None] = "0009_add_engagement_session_summaries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    # 1. Update rule_sets table columns
    if "rule_sets" in tables:
        rule_set_cols = [c["name"] for c in inspector.get_columns("rule_sets")]
        if "session_id" not in rule_set_cols:
            op.add_column("rule_sets", sa.Column("session_id", sa.String(), nullable=True))
            try:
                op.create_index("ix_rule_sets_session_id", "rule_sets", ["session_id"])
            except Exception:
                pass
        if "status" not in rule_set_cols:
            op.add_column("rule_sets", sa.Column("status", sa.String(), nullable=False, server_default="draft"))
            try:
                op.create_index("ix_rule_sets_status", "rule_sets", ["status"])
            except Exception:
                pass
        if "signature" not in rule_set_cols:
            op.add_column("rule_sets", sa.Column("signature", sa.String(), nullable=True))
        if "created_at" not in rule_set_cols:
            op.add_column("rule_sets", sa.Column("created_at", sa.DateTime(), nullable=True))
        if "updated_at" not in rule_set_cols:
            op.add_column("rule_sets", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # 2. Update application_rules columns
    if "application_rules" in tables:
        app_rule_cols = [c["name"] for c in inspector.get_columns("application_rules")]
        if "application_name" not in app_rule_cols:
            op.add_column("application_rules", sa.Column("application_name", sa.String(), nullable=True))
        if "rule_mode" not in app_rule_cols:
            op.add_column("application_rules", sa.Column("rule_mode", sa.String(), nullable=False, server_default="blocked"))
        if "category" not in app_rule_cols:
            op.add_column("application_rules", sa.Column("category", sa.String(), nullable=False, server_default="general"))

    # 3. Create website_rules table
    if "website_rules" not in tables:
        op.create_table(
            "website_rules",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("rule_set_id", sa.String(), nullable=False),
            sa.Column("domain_pattern", sa.String(), nullable=False),
            sa.Column("rule_mode", sa.String(), nullable=False, server_default="blocked"),
            sa.Column("category", sa.String(), nullable=False, server_default="general"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("reason", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id")
        )
        op.create_index("ix_website_rules_rule_set_id", "website_rules", ["rule_set_id"])
        op.create_index("ix_website_rules_domain_pattern", "website_rules", ["domain_pattern"])

    # 4. Create device_policy_requirements table
    if "device_policy_requirements" not in tables:
        op.create_table(
            "device_policy_requirements",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("rule_set_id", sa.String(), nullable=False),
            sa.Column("require_agent_enrolled", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("require_dns_or_content_filter", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("require_application_control", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("require_managed_browser_policy", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("require_usb_storage_restriction", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("required_enforcement_level", sa.String(), nullable=False, server_default="development"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("rule_set_id", name="uq_device_policy_requirements_rule_set_id")
        )
        op.create_index("ix_device_policy_requirements_rule_set_id", "device_policy_requirements", ["rule_set_id"])

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "device_policy_requirements" in tables:
        op.drop_table("device_policy_requirements")
    if "website_rules" in tables:
        op.drop_table("website_rules")
