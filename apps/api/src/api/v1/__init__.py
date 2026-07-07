"""API v1 routers."""

from fastapi import APIRouter

from src.api.v1 import auth, clinician, consent, risk_events, sessions, stt

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(sessions.router)
api_v1.include_router(clinician.router)
api_v1.include_router(risk_events.router)
api_v1.include_router(stt.router)
api_v1.include_router(consent.router)
