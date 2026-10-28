"""
System & Server Time Endpoint Router (/api/v1/system).
"""

from datetime import datetime, timezone
from fastapi import APIRouter
from ..schemas.system import ServerTimeResponse

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/time", response_model=ServerTimeResponse)
def get_server_time():
    """
    Trusted Server Time Endpoint.
    Returns the backend server's current timezone-aware UTC time and clock-skew tolerance.
    Must be served over HTTPS in production deployments.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    return ServerTimeResponse(
        server_time_utc=now_utc,
        time_zone="UTC",
        max_allowed_clock_skew_seconds=120
    )
