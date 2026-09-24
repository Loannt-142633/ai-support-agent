"""Versioned API router."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1.documents import router as documents_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api")
router.include_router(health_router)
router.include_router(users_router, prefix="/v1")
router.include_router(tickets_router, prefix="/v1")
router.include_router(documents_router, prefix="/v1")
