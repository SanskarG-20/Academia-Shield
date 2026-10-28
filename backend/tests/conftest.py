"""
Pytest Fixtures for FastAPI Backend Tests.
"""

import sys
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app.models
from app.core.database import Base, get_db, ensure_schema_up_to_date
from app.main import app

TEST_DATABASE_URL = "sqlite:///./test_academia_shield_v2.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_schema_up_to_date(engine)

@pytest.fixture
def db_session():
    from app.services.auth_service import _FAILED_ATTEMPTS
    _FAILED_ATTEMPTS.clear()
    session = TestingSessionLocal()
    # Clear all data before test in reverse dependency order
    for table in reversed(Base.metadata.sorted_tables):
        try:
            session.execute(table.delete())
        except Exception:
            pass
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
