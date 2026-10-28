"""
SQLAlchemy Database Connection & Session Management.
"""

import os
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings

def get_canonical_db_url(url: str | None = None) -> str:
    raw_url = url or settings.get_database_url()
    if not raw_url or raw_url == "postgresql+psycopg2://postgres:postgres@localhost:5432/academia_shield":
        # Fallback to local SQLite if PostgreSQL URL is default and sqlite fallback is preferred in dev
        raw_url = settings.DATABASE_URL or "sqlite:///./academia_shield_v2.db"

    # Make relative SQLite paths canonical to backend directory
    if raw_url.startswith("sqlite:///./") or raw_url == "sqlite:///academia_shield_v2.db":
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_file = os.path.join(backend_dir, "academia_shield_v2.db")
        return f"sqlite:///{db_file.replace(os.sep, '/')}"
    return raw_url

db_url = get_canonical_db_url()

connect_args = {}
engine_kwargs = {}

if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30.0
    engine_kwargs["connect_args"] = connect_args
else:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True
    })

engine = create_engine(db_url, **engine_kwargs)

if db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
            pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _get_column_sql_type(col, bind_engine) -> str:
    """Helper to determine column SQL type for ALTER TABLE."""
    try:
        return str(col.type.compile(bind_engine.dialect))
    except Exception:
        pass
    type_name = type(col.type).__name__.upper()
    if "INT" in type_name:
        return "INTEGER"
    if "BOOL" in type_name:
        return "BOOLEAN"
    if "DATE" in type_name or "TIME" in type_name:
        return "DATETIME"
    if "JSON" in type_name:
        return "JSON"
    if "FLOAT" in type_name or "REAL" in type_name or "NUMERIC" in type_name:
        return "REAL"
    return "VARCHAR"

def ensure_schema_up_to_date(bind_engine):
    """
    Automatic runtime schema migration helper.
    Ensures all tables and required columns exist on SQLite or PostgreSQL.
    Dynamically introspects all declared SQLAlchemy models and adds missing columns.
    """
    try:
        Base.metadata.create_all(bind=bind_engine)
        inspector = inspect(bind_engine)
        existing_tables = inspector.get_table_names()

        columns_by_table = {
            "sessions": [
                ("batch_id", "VARCHAR"),
                ("class_id", "VARCHAR"),
                ("rule_set_id", "VARCHAR"),
                ("description", "VARCHAR"),
                ("start_at", "DATETIME"),
                ("end_at", "DATETIME"),
                ("start_at_utc", "DATETIME"),
                ("end_at_utc", "DATETIME"),
                ("started_at", "DATETIME"),
                ("ended_at", "DATETIME"),
                ("timezone", "VARCHAR DEFAULT 'UTC'"),
                ("recurrence_type", "VARCHAR DEFAULT 'none'"),
                ("recurrence_interval", "INTEGER DEFAULT 1"),
                ("recurrence_days_of_week", "JSON"),
                ("recurrence_until_utc", "DATETIME"),
                ("status", "VARCHAR DEFAULT 'scheduled'"),
                ("is_active", "BOOLEAN DEFAULT 0"),
                ("policy_version", "INTEGER DEFAULT 1"),
                ("session_code", "VARCHAR"),
                ("idle_threshold_seconds", "INTEGER DEFAULT 60"),
                ("emergency_stopped_at", "DATETIME"),
                ("emergency_stopped_by", "VARCHAR"),
                ("emergency_stop_reason", "VARCHAR"),
                ("created_at", "DATETIME"),
                ("updated_at", "DATETIME")
            ],
            "session_participants": [
                ("status", "VARCHAR DEFAULT 'joined'"),
                ("joined_at", "DATETIME"),
                ("left_at", "DATETIME"),
                ("enforcement_activated_at", "DATETIME"),
                ("enforcement_stop_reason", "VARCHAR"),
                ("policy_acknowledged_at", "DATETIME")
            ],
            "rule_sets": [
                ("batch_id", "VARCHAR"),
                ("session_id", "VARCHAR"),
                ("class_id", "VARCHAR"),
                ("name", "VARCHAR"),
                ("version", "INTEGER DEFAULT 1"),
                ("status", "VARCHAR DEFAULT 'draft'"),
                ("is_active", "BOOLEAN DEFAULT 1"),
                ("issued_at", "DATETIME"),
                ("expires_at", "DATETIME"),
                ("created_by", "VARCHAR"),
                ("integrity_hash", "VARCHAR"),
                ("signature", "VARCHAR"),
                ("created_at", "DATETIME"),
                ("updated_at", "DATETIME")
            ],
            "application_rules": [
                ("application_name", "VARCHAR"),
                ("executable_name", "VARCHAR"),
                ("executable_path_pattern", "VARCHAR"),
                ("trusted_hash", "VARCHAR"),
                ("rule_mode", "VARCHAR DEFAULT 'blocked'"),
                ("category", "VARCHAR DEFAULT 'general'"),
                ("action", "VARCHAR DEFAULT 'close'"),
                ("priority", "INTEGER DEFAULT 0"),
                ("is_enabled", "BOOLEAN DEFAULT 1"),
                ("reason", "VARCHAR"),
                ("cooldown_seconds", "INTEGER DEFAULT 0")
            ],
            "website_rules": [
                ("rule_set_id", "VARCHAR"),
                ("domain_pattern", "VARCHAR"),
                ("rule_mode", "VARCHAR DEFAULT 'blocked'"),
                ("category", "VARCHAR DEFAULT 'general'"),
                ("priority", "INTEGER DEFAULT 10"),
                ("is_enabled", "BOOLEAN DEFAULT 1"),
                ("reason", "VARCHAR")
            ],
            "device_policy_requirements": [
                ("rule_set_id", "VARCHAR"),
                ("require_agent_enrolled", "BOOLEAN DEFAULT 1"),
                ("require_dns_or_content_filter", "BOOLEAN DEFAULT 1"),
                ("require_application_control", "BOOLEAN DEFAULT 1"),
                ("require_managed_browser_policy", "BOOLEAN DEFAULT 0"),
                ("require_usb_storage_restriction", "BOOLEAN DEFAULT 0"),
                ("required_enforcement_level", "VARCHAR DEFAULT 'development'")
            ],
            "users": [
                ("institutional_id", "VARCHAR"),
                ("department", "VARCHAR"),
                ("roll_number", "VARCHAR"),
                ("year", "VARCHAR"),
                ("designation", "VARCHAR")
            ],
            "batches": [
                ("professor_id", "VARCHAR"),
                ("name", "VARCHAR"),
                ("description", "VARCHAR"),
                ("batch_code", "VARCHAR"),
                ("is_active", "BOOLEAN DEFAULT 1")
            ],
            "agent_devices": [
                ("platform_version", "VARCHAR"),
                ("enrollment_status", "VARCHAR DEFAULT 'enrolled'"),
                ("capabilities_json", "JSON"),
                ("compliance_status", "VARCHAR DEFAULT 'compliant'"),
                ("compliance_level", "VARCHAR DEFAULT 'personal'"),
                ("policy_delivery_state", "VARCHAR DEFAULT 'idle'"),
                ("last_policy_id", "VARCHAR"),
                ("created_at", "DATETIME")
            ],
            "engagement_feature_windows": [
                ("allowed_academic_application_active_seconds", "FLOAT DEFAULT 0.0"),
                ("allowed_academic_website_active_seconds", "FLOAT DEFAULT 0.0"),
                ("unknown_or_unavailable_seconds", "FLOAT DEFAULT 0.0"),
                ("active_resource_sample_count", "INTEGER DEFAULT 0"),
                ("unknown_resource_sample_count", "INTEGER DEFAULT 0"),
                ("feature_completeness_percent", "FLOAT DEFAULT 100.0"),
                ("approved_resources_breakdown", "JSON")
            ],
            "engagement_session_summaries": [
                ("allowed_academic_application_active_seconds", "FLOAT DEFAULT 0.0"),
                ("allowed_academic_website_active_seconds", "FLOAT DEFAULT 0.0"),
                ("unknown_or_unavailable_seconds", "FLOAT DEFAULT 0.0"),
                ("active_resource_sample_count", "INTEGER DEFAULT 0"),
                ("unknown_resource_sample_count", "INTEGER DEFAULT 0"),
                ("feature_completeness_percent", "FLOAT DEFAULT 100.0"),
                ("approved_resources_breakdown", "JSON")
            ]
        }

        with bind_engine.connect() as conn:
            # Migration check for rule_sets class_id column on SQLite
            if str(bind_engine.url).startswith("sqlite") and "rule_sets" in existing_tables:
                try:
                    table_info = conn.execute(text("PRAGMA table_info(rule_sets)")).fetchall()
                    class_id_col = next((c for c in table_info if c[1] == "class_id"), None)
                    if class_id_col and class_id_col[3] == 1:
                        conn.execute(text("PRAGMA foreign_keys=OFF"))
                        conn.execute(text("""
                            CREATE TABLE rule_sets_new (
                                id VARCHAR NOT NULL PRIMARY KEY,
                                batch_id VARCHAR,
                                class_id VARCHAR,
                                name VARCHAR NOT NULL,
                                version INTEGER NOT NULL DEFAULT 1,
                                is_active BOOLEAN NOT NULL DEFAULT 1,
                                issued_at DATETIME NOT NULL,
                                expires_at DATETIME,
                                created_by VARCHAR NOT NULL,
                                integrity_hash VARCHAR NOT NULL
                            )
                        """))
                        existing_cols = [c[1] for c in table_info]
                        col_list = ", ".join(existing_cols)
                        conn.execute(text(f"INSERT INTO rule_sets_new ({col_list}) SELECT {col_list} FROM rule_sets"))
                        conn.execute(text("DROP TABLE rule_sets"))
                        conn.execute(text("ALTER TABLE rule_sets_new RENAME TO rule_sets"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_rule_sets_batch_id ON rule_sets (batch_id)"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_rule_sets_class_id ON rule_sets (class_id)"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_rule_sets_is_active ON rule_sets (is_active)"))
                        conn.execute(text("PRAGMA foreign_keys=ON"))
                        conn.commit()
                        inspector = inspect(bind_engine)
                        existing_tables = inspector.get_table_names()
                except Exception:
                    pass

            # Migration check for sessions class_id / start_at / end_at columns on SQLite
            if str(bind_engine.url).startswith("sqlite") and "sessions" in existing_tables:
                try:
                    table_info = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
                    class_id_col = next((c for c in table_info if c[1] == "class_id"), None)
                    start_at_col = next((c for c in table_info if c[1] == "start_at"), None)
                    end_at_col = next((c for c in table_info if c[1] == "end_at"), None)
                    needs_migration = False
                    if class_id_col and class_id_col[3] == 1:
                        needs_migration = True
                    if start_at_col and start_at_col[3] == 1:
                        needs_migration = True
                    if end_at_col and end_at_col[3] == 1:
                        needs_migration = True

                    if needs_migration:
                        conn.execute(text("PRAGMA foreign_keys=OFF"))
                        conn.execute(text("""
                            CREATE TABLE sessions_new (
                                id VARCHAR NOT NULL PRIMARY KEY,
                                batch_id VARCHAR,
                                class_id VARCHAR,
                                rule_set_id VARCHAR,
                                created_by VARCHAR NOT NULL,
                                title VARCHAR NOT NULL,
                                start_at DATETIME,
                                end_at DATETIME,
                                start_at_utc DATETIME NOT NULL,
                                end_at_utc DATETIME NOT NULL,
                                timezone VARCHAR NOT NULL DEFAULT 'UTC',
                                recurrence_type VARCHAR NOT NULL DEFAULT 'none',
                                recurrence_interval INTEGER NOT NULL DEFAULT 1,
                                recurrence_days_of_week JSON,
                                recurrence_until_utc DATETIME,
                                status VARCHAR NOT NULL DEFAULT 'scheduled',
                                is_active BOOLEAN NOT NULL DEFAULT 0,
                                policy_version INTEGER NOT NULL DEFAULT 1,
                                created_at DATETIME NOT NULL,
                                updated_at DATETIME NOT NULL,
                                FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE CASCADE,
                                FOREIGN KEY(class_id) REFERENCES classes (id) ON DELETE CASCADE,
                                FOREIGN KEY(rule_set_id) REFERENCES rule_sets (id) ON DELETE SET NULL,
                                FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE CASCADE
                            )
                        """))
                        existing_cols = [c[1] for c in table_info]
                        col_list = ", ".join(existing_cols)
                        conn.execute(text(f"INSERT INTO sessions_new ({col_list}) SELECT {col_list} FROM sessions"))
                        conn.execute(text("DROP TABLE sessions"))
                        conn.execute(text("ALTER TABLE sessions_new RENAME TO sessions"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_batch_id ON sessions (batch_id)"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_class_id ON sessions (class_id)"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_rule_set_id ON sessions (rule_set_id)"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions (status)"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_is_active ON sessions (is_active)"))
                        conn.execute(text("PRAGMA foreign_keys=ON"))
                        conn.commit()
                        inspector = inspect(bind_engine)
                        existing_tables = inspector.get_table_names()
                except Exception:
                    pass

            # 1. Apply explicit fallback columns
            for table_name, cols in columns_by_table.items():
                if table_name in existing_tables:
                    existing_cols = [c["name"] for c in inspector.get_columns(table_name)]
                    for col_name, col_type in cols:
                        if col_name not in existing_cols:
                            try:
                                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                                conn.commit()
                            except Exception:
                                pass

            # 2. Dynamic Auto-Migration: introspect ALL declared models in Base.metadata
            inspector = inspect(bind_engine)
            existing_tables = inspector.get_table_names()
            for table_name, table_obj in Base.metadata.tables.items():
                if table_name in existing_tables:
                    try:
                        existing_col_names = {c["name"] for c in inspector.get_columns(table_name)}
                        for col in table_obj.columns:
                            if col.name not in existing_col_names:
                                col_sql = _get_column_sql_type(col, bind_engine)
                                try:
                                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_sql}"))
                                    conn.commit()
                                except Exception:
                                    pass
                    except Exception:
                        pass
    except Exception:
        pass
