"""FastAPI application composition root."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.notifications import TicketConnectionManager, notification_lifespan
from app.api.notifications import router as notifications_router
from app.api.router import router as api_router
from app.api.v1.agent import router as agent_router
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application and wire its outer adapters."""

    settings = settings or get_settings()
    manager = TicketConnectionManager()
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lambda _app: notification_lifespan(settings, manager),
    )
    application.state.settings = settings
    application.state.notification_manager = manager
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    application.include_router(notifications_router)
    if settings.demo_staff_auth_enabled:
        if settings.app_env != "local":
            raise RuntimeError("Demo agent cannot start outside the local environment")
        application.include_router(agent_router, prefix="/api/v1")
    return application


app = create_app()


def run() -> None:
    """Run the local development server."""

    host = "127.0.0.1" if get_settings().demo_staff_auth_enabled else "0.0.0.0"
    uvicorn.run("app.main:app", host=host, port=8000, reload=True)
