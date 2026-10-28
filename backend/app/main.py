"""
Academia Shield FastAPI Main Application.
"""

import sys
import os

# Ensure backend directory is in sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import uvicorn
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base
from app.utils.request_id import RequestIDMiddleware, create_error_response
from app.routers import (
    auth_router,
    classes_router,
    sessions_router,
    rules_router,
    agent_router,
    dashboard_router,
    system_router,
    batches_router,
    admin_router,
    engagement_router,
    admin_ml_router
)

# Initialize database tables
import app.models
from app.core.database import ensure_schema_up_to_date
Base.metadata.create_all(bind=engine)
ensure_schema_up_to_date(engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production Academic Network Governance & Classroom Session API",
    version="2.1.0",
    docs_url="/docs" if settings.SHOW_DOCS else None,
    redoc_url="/redoc" if settings.SHOW_DOCS else None
)

# Middlewares
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    error_code = "HTTP_ERROR"
    if exc.status_code == 401:
        error_code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        error_code = "FORBIDDEN"
    elif exc.status_code == 404:
        error_code = "NOT_FOUND"
    elif exc.status_code == 400:
        error_code = "BAD_REQUEST"

    return create_error_response(
        status_code=exc.status_code,
        error_code=error_code,
        message=str(exc.detail),
        request_id=request_id
    )

from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    status_code = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
    return create_error_response(
        status_code=status_code,
        error_code="VALIDATION_ERROR",
        message="Request payload validation failed",
        details=jsonable_encoder(exc.errors()),
        request_id=request_id
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred",
        details=str(exc),
        request_id=request_id
    )

from app.core.sockets import sio_app
from fastapi.staticfiles import StaticFiles

# Mount Socket.IO Real-time Engine
app.mount("/socket.io", sio_app)

# Mount Static Installers Directory for Windows and macOS releases
installers_dir = os.path.join(BACKEND_DIR, "installers")
os.makedirs(installers_dir, exist_ok=True)
app.mount("/installers", StaticFiles(directory=installers_dir), name="installers")

# Mount Versioned Routers under /api/v1 and /api
app.include_router(auth_router, prefix=settings.API_V1_STR)

app.include_router(auth_router, prefix="/api")
app.include_router(classes_router, prefix=settings.API_V1_STR)
app.include_router(classes_router, prefix="/api")
app.include_router(batches_router, prefix=settings.API_V1_STR)
app.include_router(batches_router, prefix="/api")
app.include_router(sessions_router, prefix=settings.API_V1_STR)
app.include_router(sessions_router, prefix="/api")
app.include_router(rules_router, prefix=settings.API_V1_STR)
app.include_router(rules_router, prefix="/api")
app.include_router(agent_router, prefix=settings.API_V1_STR)
app.include_router(agent_router, prefix="/api")
app.include_router(dashboard_router, prefix=settings.API_V1_STR)
app.include_router(dashboard_router, prefix="/api")
app.include_router(system_router, prefix=settings.API_V1_STR)
app.include_router(system_router, prefix="/api")
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix="/api")
app.include_router(engagement_router, prefix=settings.API_V1_STR)
app.include_router(engagement_router, prefix="/api")
app.include_router(admin_ml_router, prefix=settings.API_V1_STR)
app.include_router(admin_ml_router, prefix="/api")

@app.get("/")
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": "2.1.0",
        "message": "Academia Shield Production FastAPI Backend is operational."
    }

@app.get("/health", tags=["Health"])
@app.get(f"{settings.API_V1_STR}/health", tags=["Health"])
def health_check():
    db_status = "connected"
    try:
        from app.core.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if "unhealthy" not in db_status else "degraded",
        "service": settings.PROJECT_NAME,
        "version": "2.1.0",
        "database": db_status
    }

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
