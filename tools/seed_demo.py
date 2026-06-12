"""Seed a demo dataset for the clinician dashboard.

Usage (from apps/api):
    cd apps/api && uv run python ../../tools/seed_demo.py

Idempotent — running twice updates passwords + ensures the demo objects exist.
Creates:
- 1 clinician (doc@demo.local / Doctor!Password-2026)
- 2 patients (alice@demo.local + bob@demo.local, both with Hunter2-Strong!Password)
- 1 session per patient
- Several messages
- A `critical` risk_event on Bob's session

Designed to run against the dev Postgres container (`infra/deploy/docker-compose.yml`).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path


# Make `src` importable when invoked from repo root.
APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)


async def main() -> None:
    # Imports must happen after sys.path manipulation.
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.core.config import get_settings
    from src.core.encryption import encrypt_str
    from src.core.security import hash_password
    from src.models.consent import ConsentSnapshot
    from src.models.patient_profile import PatientProfile
    from src.models.session import Message, RiskEvent, Session
    from src.models.user import User

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    def _profile_aad(user_id: uuid.UUID, column: str) -> bytes:
        return f"patient_profiles.{column}:{user_id}".encode()

    def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
        return f"messages.content:{session_id}:{message_id}".encode()

    async with SessionLocal() as db:
        # ── Clinician ─────────────────────────────
        clinician_email = "doc@demo.local"
        existing = await db.execute(
            select(User).where(User.email == clinician_email)
        )
        clinician = existing.scalar_one_or_none()
        if clinician is None:
            clinician = User(
                email=clinician_email,
                password_hash=hash_password("Doctor!Password-2026", settings),
                role="clinician",
            )
            db.add(clinician)
        else:
            clinician.password_hash = hash_password("Doctor!Password-2026", settings)
        await db.flush()

        # ── Patients ──────────────────────────────
        def upsert_patient(
            email: str, name: str, birth_year: int, phone: str, emergency: str
        ) -> User:
            return User(
                email=email,
                password_hash=hash_password("Hunter2-Strong!Password", settings),
                role="patient",
            )

        async def ensure_patient(
            email: str,
            *,
            name: str,
            birth_year: int,
            phone: str,
            emergency: str,
            risk_opt_in: bool,
        ) -> User:
            row = await db.execute(select(User).where(User.email == email))
            user = row.scalar_one_or_none()
            if user is None:
                user = upsert_patient(email, name, birth_year, phone, emergency)
                db.add(user)
                await db.flush()
                db.add(
                    PatientProfile(
                        user_id=user.id,
                        name_encrypted=encrypt_str(
                            name, aad=_profile_aad(user.id, "name"), settings=settings
                        ),
                        birth_year=birth_year,
                        gender="female",
                        phone_encrypted=encrypt_str(
                            phone,
                            aad=_profile_aad(user.id, "phone"),
                            settings=settings,
                        ),
                        region="서울 강남구",
                        emergency_contact_encrypted=encrypt_str(
                            emergency,
                            aad=_profile_aad(user.id, "emergency_contact"),
                            settings=settings,
                        ),
                    )
                )
                db.add(
                    ConsentSnapshot(
                        user_id=user.id,
                        tos=True,
                        privacy=True,
                        sensitive=True,
                        risk_notification=risk_opt_in,
                        tos_version="demo",
                        privacy_version="demo",
                    )
                )
            return user

        alice = await ensure_patient(
            "alice@demo.local",
            name="앨리스",
            birth_year=1995,
            phone="01011112222",
            emergency="01033334444",
            risk_opt_in=True,
        )
        bob = await ensure_patient(
            "bob@demo.local",
            name="박범수",
            birth_year=1988,
            phone="01055556666",
            emergency="01077778888",
            risk_opt_in=False,
        )

        # ── Sessions + messages + risk_event ──────
        async def has_session(user_id: uuid.UUID) -> bool:
            row = await db.execute(
                select(Session).where(Session.patient_id == user_id).limit(1)
            )
            return row.scalar_one_or_none() is not None

        if not await has_session(alice.id):
            sess = Session(
                patient_id=alice.id,
                status="in_progress",
                created_at=datetime.now(tz=UTC) - timedelta(hours=2),
            )
            db.add(sess)
            await db.flush()
            for i, content in enumerate(
                [
                    "요즘 2주째 잠을 잘 못 자고 있어요",
                    "식욕도 떨어졌고 의욕이 없어요",
                    "주말에는 그래도 조금 나아요",
                ]
            ):
                mid = uuid.uuid4()
                db.add(
                    Message(
                        id=mid,
                        session_id=sess.id,
                        role="user",
                        content_encrypted=encrypt_str(
                            content,
                            aad=_message_aad(sess.id, mid),
                            settings=settings,
                        ),
                        input_modality="text",
                        created_at=sess.created_at + timedelta(minutes=2 * i),
                    )
                )

        if not await has_session(bob.id):
            sess = Session(
                patient_id=bob.id,
                status="in_progress",
                created_at=datetime.now(tz=UTC) - timedelta(minutes=30),
            )
            db.add(sess)
            await db.flush()
            critical_mid = uuid.uuid4()
            db.add(
                Message(
                    id=critical_mid,
                    session_id=sess.id,
                    role="user",
                    content_encrypted=encrypt_str(
                        "더 이상 살고 싶지 않아요",
                        aad=_message_aad(sess.id, critical_mid),
                        settings=settings,
                    ),
                    input_modality="text",
                )
            )
            db.add(
                RiskEvent(
                    patient_id=bob.id,
                    session_id=sess.id,
                    level="critical",
                    category="suicide",
                    trigger_message_id=critical_mid,
                    ai_evidence={
                        "matched_keywords": ["살고 싶지 않"],
                        "classifier": "keyword-v1",
                        "confidence": 0.95,
                        "latency_ms": 4,
                    },
                    status="detected",
                    legal_basis="self_hotline_only",  # Bob opted out
                )
            )

        await db.commit()
        print("✓ Seed complete")
        print(f"  clinician: {clinician_email} / Doctor!Password-2026")
        print("  patients: alice@demo.local, bob@demo.local / Hunter2-Strong!Password")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
