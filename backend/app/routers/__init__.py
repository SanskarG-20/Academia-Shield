"""
API Routers Package.
"""

from .auth import router as auth_router
from .classes import router as classes_router
from .sessions import router as sessions_router
from .rules import router as rules_router
from .agent import router as agent_router
from .dashboard import router as dashboard_router
from .system import router as system_router
from .batches import router as batches_router
from .admin import router as admin_router
from .engagement import router as engagement_router
from .admin_ml import router as admin_ml_router

__all__ = [
    "auth_router",
    "classes_router",
    "sessions_router",
    "rules_router",
    "agent_router",
    "dashboard_router",
    "system_router",
    "batches_router",
    "admin_router",
    "engagement_router",
    "admin_ml_router",
]
