"""AI dialogue turn orchestration (FR-004).

Called by the WebSocket gateway after the safety check clears (LOW/MEDIUM). It:
1. builds the conversation context (decrypted, oldest-first) for the AI server,
2. calls POST /ai/chat/respond,
3. persists the assistant reply (encrypted, AAD-bound like user messages),
4. updates the session's intake progress (ratio + collected items),
5. returns the `ai:complete` payload (camelCase) for the client.

Best-effort by design: ANY failure returns None so the chat keeps flowing — the
safety pipeline has already done its job and the dialogue is non-critical. Token
streaming (`ai:token`) is deferred until the AI server exposes SSE.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from contracts.chat import ChatMessage, ChatRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.encryption import decrypt_str, encrypt_str
from src.models.session import Message, Session
from src.services.ai_client import AIClient, AIClientError

logger = logging.getLogger(__name__)

CHAT_CONTEXT_TURNS = 20


def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


async def _recent_messages(
    db: AsyncSession, session_id: uuid.UUID, *, limit: int
) -> list[ChatMessage]:
    rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    msgs = list(rows.scalars().all())
    msgs.reverse()  # oldest-first for the model
    out: list[ChatMessage] = []
    for m in msgs:
        try:
            content = decrypt_str(
                m.content_encrypted, aad=_message_aad(session_id, m.id)
            )
        except Exception:
            continue  # skip an unreadable turn rather than poison the context
        out.append(ChatMessage(role=m.role, content=content))
    return out


async def respond(
    db: AsyncSession,
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    settings: Settings,
) -> dict[str, Any] | None:
    """Generate + persist one assistant turn. Returns the ai:complete payload
    or None if generation failed (caller simply omits the AI reply)."""
    try:
        context = await _recent_messages(db, session_id, limit=CHAT_CONTEXT_TURNS)
        result = await ai_client.chat_respond(
            ChatRequest(session_id=session_id, messages=context)
        )
    except AIClientError as exc:
        logger.info("chat.respond.unavailable", extra={"error": str(exc)})
        return None
    except Exception:  # noqa: BLE001 — dialogue is best-effort, never break the WS
        logger.warning("chat.respond.failed", exc_info=True)
        return None

    # Persist the assistant reply (AAD bound to its own row id).
    ai_message_id = uuid.uuid4()
    db.add(
        Message(
            id=ai_message_id,
            session_id=session_id,
            role="ai",
            content_encrypted=encrypt_str(
                result.reply,
                aad=_message_aad(session_id, ai_message_id),
                settings=settings,
            ),
            input_modality="text",
        )
    )

    # Persist the latest progress snapshot on the session.
    ratio = max(0.0, min(1.0, result.progress.ratio))
    sess_row = await db.execute(select(Session).where(Session.id == session_id))
    sess = sess_row.scalar_one_or_none()
    if sess is not None:
        sess.progress_ratio = ratio
        sess.collected_items = result.progress.collected_items

    return {
        "messageId": str(ai_message_id),
        "content": result.reply,
        "modelUsed": result.model_used,
        "progress": {
            "collectedItems": result.progress.collected_items,
            "totalItems": result.progress.total_items,
            "ratio": ratio,
        },
    }
