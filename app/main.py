"""FastAPI application composition root."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build the application and wire its outer adapters."""

    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    return application


app = create_app()


def run() -> None:
    """Run the local development server."""

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
