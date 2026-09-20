"""NoInsta Backend FastAPI application."""

from contextlib import asynccontextmanager
import logging
import sys
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.devices import router as devices_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.pairing import router as pairing_router
from app.api.settings import settings_router
from app.core.config import settings
from app.websocket.laptop import router as websocket_router

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)-7s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("noinsta.server")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown events."""
    logger.info("Starting NoInsta Backend Server (environment: %s)", settings.APP_ENV)
    yield
    logger.info("Shutting down NoInsta Backend Server...")


# FastAPI Application instance
app = FastAPI(
    title="NoInsta Backend Server",
    description="Central authority for NoInsta authentication, pairing, presence, and intervention routing.",
    version="1.0.0",
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
    lifespan=lifespan,
)

# CORS Configuration
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


# Exception Handlers for consistent API error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers or {},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Request validation failed.",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# Register Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(pairing_router)
app.include_router(devices_router)
app.include_router(events_router)
app.include_router(analytics_router)
app.include_router(settings_router)
app.include_router(websocket_router)
