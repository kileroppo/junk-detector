"""Web UI sub-routers — combined into a single router."""

from fastapi import APIRouter

from src.web.routes.api import router as api_router
from src.web.routes.pages import router as pages_router
from src.web.routes.partials import router as partials_router

router = APIRouter()
router.include_router(pages_router)
router.include_router(partials_router)
router.include_router(api_router)

__all__ = ["router"]
