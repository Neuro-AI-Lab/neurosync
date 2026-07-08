"""Bearer-token auth for the RAG router ONLY (ADR-013 option (a), VAL-005).

VAL-005: `POST /ai/rag/grounding` was reachable unauthenticated at a hardcoded
public IP, with a patient UUID acting as a de facto access credential. This
module adds env-based bearer-token auth to `src.rag.route`'s router only —
every other router (safety/handoff/chat/slots/survey/sentiment/temporal) is
untouched.

Fail-closed default: if `NS_RAG_API_KEY` is unset, requests are refused with
503 (service unavailable) — NOT silently allowed through. The only opt-out is
`NS_RAG_DEV_MODE=1`, an explicit, logged, local-development-only bypass.
Never enable `NS_RAG_DEV_MODE` outside a developer's own machine.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def _dev_mode_enabled() -> bool:
    return os.getenv("NS_RAG_DEV_MODE", "0").strip().lower() in _TRUTHY


async def require_rag_api_key(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency for the RAG router — never logs key values.

    - `NS_RAG_DEV_MODE=1` → auth disabled (explicit, logged, dev-only opt-out).
    - `NS_RAG_API_KEY` unset (and dev mode not enabled) → 503 (fail-closed:
      an unconfigured deployment refuses to serve, it does not silently open).
    - Missing/malformed `Authorization: Bearer <key>` header → 401.
    - Mismatched key (constant-time compare) → 403.
    """
    if _dev_mode_enabled():
        logger.warning(
            "rag.auth.dev_mode_bypass — NS_RAG_DEV_MODE=1, RAG router auth is "
            "DISABLED. This must never be set outside local development."
        )
        return

    expected = os.getenv("NS_RAG_API_KEY", "").strip()
    if not expected:
        logger.error("rag.auth.unconfigured — NS_RAG_API_KEY not set, refusing request (503)")
        raise HTTPException(
            status_code=503,
            detail="RAG API key not configured — service unavailable",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    presented = authorization[len("Bearer "):].strip()
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=403, detail="Invalid API key")
