"""CareFund-AI FastAPI entry point."""

from fastapi import FastAPI

from .errors import register_exception_handlers
from .routes.applications import router as applications_router
from .routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="CareFund-AI Backend",
        version="1.0.0",
        description="Contract-first local backend with persistent state and pluggable adapters.",
    )
    register_exception_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(applications_router, prefix="/api/v1")
    return app


app = create_app()

