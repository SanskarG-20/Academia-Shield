"""
System Pydantic Schemas.
"""

from pydantic import BaseModel

class ServerTimeResponse(BaseModel):
    server_time_utc: str
    time_zone: str = "UTC"
    max_allowed_clock_skew_seconds: int = 120
