"""
Request ID and Error Utilities.
"""

import uuid
from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Injects unique X-Request-ID header into every HTTP request and response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[Any] = None,
    request_id: Optional[str] = None
) -> JSONResponse:
    """Format consistent standard JSON error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "details": details,
            "request_id": request_id
        }
    )
