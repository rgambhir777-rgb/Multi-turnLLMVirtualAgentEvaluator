"""All API routers, mounted under /api."""
from fastapi import APIRouter

from . import agents, journeys, knowledge, runs, scripts, system

api_router = APIRouter(prefix="/api")
for module in (system, agents, knowledge, journeys, scripts, runs):
    api_router.include_router(module.router)

__all__ = ["api_router"]
