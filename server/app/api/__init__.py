"""API package exports."""

from .auth import router as auth_router
from .devices import router as devices_router
from .events import router as events_router
from .health import router as health_router
from .pairing import router as pairing_router

__all__ = [
    "auth_router",
    "devices_router",
    "events_router",
    "health_router",
    "pairing_router",
]
