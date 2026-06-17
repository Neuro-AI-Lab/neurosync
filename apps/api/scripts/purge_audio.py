"""One-shot audio purge — cron / Celery Beat entrypoint (FR-036).

Deletes original audio files past their 48h retention window and marks
`deleted_at`. Transcriptions are retained. Run from apps/api:

    uv run python -m scripts.purge_audio
"""

from __future__ import annotations

import asyncio

from src.db import SessionLocal
from src.services.stt import purge_expired_audio


async def _main() -> int:
    async with SessionLocal() as db:
        return await purge_expired_audio(db)


if __name__ == "__main__":
    purged = asyncio.run(_main())
    print(f"purged {purged} expired audio recording(s)")
