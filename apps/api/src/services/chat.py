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

from contracts.chat import ChatMessage, ChatRequest, Grounding
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


async def _build_grounding(
    db: AsyncSession, session_id: uuid.UUID, context: list[ChatMessage]
) -> Grounding | None:
    """pgvector RAG grounding (best-effort — 검색 실패해도 대화는 계속 진행).

    rag 의존성/스키마/임베딩이 아직 없으면 조용히 None (대화 비크리티컬).

    NOTE: RAG 코드(src.rag)가 ai-server로 이전됨 → api에는 더 이상 없으므로
    아래 `from src.rag.retrieval import ...`가 ImportError → grounding은 항상 None.
    즉 현재 api 라이브챗은 grounding 없이 동작(degrade). RAG는 ai-server에서만 구동."""
    last_user = next((m.content for m in reversed(context) if m.role == "user"), None)
    if not last_user:
        return None
    try:
        from src.rag.retrieval import retrieve_grounding

        sess = (
            await db.execute(select(Session).where(Session.id == session_id))
        ).scalar_one_or_none()
        patient_id = sess.patient_id if sess is not None else None
        return await retrieve_grounding(db, last_user, patient_id=patient_id)
    except Exception:  # noqa: BLE001 — grounding is best-effort
        logger.info("chat.grounding.skipped", exc_info=True)
        return None


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
        grounding = await _build_grounding(db, session_id, context)
        result = await ai_client.chat_respond(
            ChatRequest(session_id=session_id, messages=context, grounding=grounding)
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
