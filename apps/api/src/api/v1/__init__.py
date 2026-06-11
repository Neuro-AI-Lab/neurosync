"""API v1 routers."""

from fastapi import APIRouter

from src.api.v1 import auth, sessions

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(sessions.router)
