"""Demo seed — clinician + 4 patient personas with varied severity (demo prep).

Idempotent: re-running skips if the clinician seed account already exists.
Creates realistic intake data (profiles, consent, sessions, messages,
PHQ-9/GAD-7, risk events, and ready Handoff reports) so the clinician dashboard
renders a full demo WITHOUT needing apps/ai-server.

Run from apps/api:
    uv run python -m scripts.seed_demo

Demo logins (all password: Demo!Password-2026):
    clinician@neurosync.demo  (clinician)
    minjun@demo / seoyeon@demo / jiho@demo / yujin@demo  (patients)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from src.core.config import Settings, get_settings
from src.core.encryption import encrypt_str
from src.core.security import hash_password
from src.db import SessionLocal
from src.models.consent import ConsentSnapshot
from src.models.handoff import HandoffReport
from src.models.patient_profile import PatientProfile
from src.models.questionnaire import QuestionnaireResult
from src.models.session import Message, RiskEvent, Session
from src.models.user import Organization, User

DEMO_PASSWORD = "Demo!Password-2026"
CLINICIAN_EMAIL = "clinician@neurosync.demo"


def _profile_aad(user_id: uuid.UUID, column: str) -> bytes:
    return f"patient_profiles.{column}:{user_id}".encode()


def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


def _severity_phq9(score: int) -> str:
    return (
        "minimal" if score <= 4 else "mild" if score <= 9 else "moderate"
        if score <= 14 else "moderately_severe" if score <= 19 else "severe"
    )


def _severity_gad7(score: int) -> str:
    return (
        "minimal" if score <= 4 else "mild" if score <= 9
        else "moderate" if score <= 14 else "severe"
    )


# (email, name, birth_year, gender, phone, region, emergency, phq9, gad7,
#  utterances, risk(level/category or None), report_narrative or None)
PERSONAS = [
    {
        "email": "minjun@demo",
        "name": "김민준",
        "birth_year": 1994,
        "gender": "male",
        "phone": "01012340001",
        "region": "서울 강남구",
        "emergency": "01099990001",
        "phq9": [1, 1, 1, 1, 1, 0, 1, 1, 0],  # 7 mild
        "gad7": [1, 1, 0, 1, 0, 1, 0],  # 4 minimal
        "messages": [
            "요즘 일이 많아서 잠을 잘 못 자요.",
            "주말에도 쉬는 느낌이 잘 안 들어요.",
        ],
        "risk": None,
        "narrative": {
            "chief_complaint": "업무 스트레스로 인한 수면 곤란",
            "present_illness": "약 2주 전부터 입면이 어렵고 주간 피로감 호소.",
            "symptoms": ["수면 곤란", "피로감"],
            "onset": "약 2주 전",
            "recent_changes": "업무량 증가",
            "triggers": ["야근 증가"],
            "sleep_appetite_activity": {
                "sleep": "입면 곤란",
                "appetite": "변화 없음",
                "activity": "유지",
            },
            "psych_history": "없음",
            "medications": "없음",
            "documents_summary": [],
            "clinician_attention": ["수면 위생 상담 권장"],
            "evidence": [],
            "latency_ms": 0,
        },
    },
    {
        "email": "seoyeon@demo",
        "name": "이서연",
        "birth_year": 1990,
        "gender": "female",
        "phone": "01012340002",
        "region": "경기 성남시",
        "emergency": "01099990002",
        "phq9": [2, 2, 2, 1, 2, 1, 1, 2, 1],  # 14 moderate
        "gad7": [2, 2, 1, 2, 1, 2, 1],  # 11 moderate
        "messages": [
            "한 달 넘게 우울한 기분이 계속돼요.",
            "예전에 즐기던 것들이 이제 재미가 없어요.",
            "가끔 다 부질없다는 생각이 들어요.",
        ],
        "risk": ("low", "passive_ideation"),
        "narrative": {
            "chief_complaint": "지속되는 우울감과 흥미 저하",
            "present_illness": "약 한 달간 우울감, 무쾌감, 수동적 부정 사고 동반.",
            "symptoms": ["우울감", "무쾌감", "식욕 저하"],
            "onset": "약 4주 전",
            "recent_changes": "사회 활동 감소",
            "triggers": ["대인관계 갈등"],
            "sleep_appetite_activity": {
                "sleep": "잦은 각성",
                "appetite": "감소",
                "activity": "회피 경향",
            },
            "psych_history": "없음",
            "medications": "없음",
            "documents_summary": [],
            "clinician_attention": ["수동적 자살사고 모니터링 필요"],
            "evidence": [],
            "latency_ms": 0,
        },
    },
    {
        "email": "jiho@demo",
        "name": "박지호",
        "birth_year": 1998,
        "gender": "male",
        "phone": "01012340003",
        "region": "서울 마포구",
        "emergency": "01099990003",
        "phq9": [3, 3, 2, 3, 2, 3, 2, 2, 2],  # 22 severe
        "gad7": [3, 3, 2, 3, 2, 3, 2],  # 18 severe
        "messages": [
            "더 이상 버틸 자신이 없어요.",
            "차라리 사라지고 싶다는 생각이 자꾸 들어요.",
        ],
        "risk": ("critical", "suicide"),
        "narrative": {
            "chief_complaint": "심한 우울감과 자살 사고",
            "present_illness": "최근 증상 급격히 악화, 적극적 자살 사고 호소.",
            "symptoms": ["심한 우울감", "절망감", "불면", "식욕 저하"],
            "onset": "약 6주 전, 최근 2주 악화",
            "recent_changes": "급격한 기능 저하",
            "triggers": ["학업 실패", "고립"],
            "sleep_appetite_activity": {
                "sleep": "심한 불면",
                "appetite": "현저한 감소",
                "activity": "거의 중단",
            },
            "psych_history": "없음(첫 내원)",
            "medications": "없음",
            "documents_summary": [],
            "clinician_attention": [
                "⚠️ 적극적 자살사고 — 즉각적 안전 평가 필요",
                "보호자 동반 및 입원 고려",
            ],
            "evidence": [],
            "latency_ms": 0,
        },
    },
    {
        "email": "yujin@demo",
        "name": "최유진",
        "birth_year": 1996,
        "gender": "female",
        "phone": "01012340004",
        "region": "인천 연수구",
        "emergency": "01099990004",
        "phq9": [1, 2, 2, 2, 1, 1, 1, 0, 0],  # 10 moderate
        "gad7": [3, 3, 2, 2, 2, 2, 2],  # 16 severe
        "messages": [
            "사소한 일에도 계속 불안하고 초조해요.",
            "심장이 두근거리고 가만히 있기가 힘들어요.",
        ],
        "risk": None,
        "narrative": {
            "chief_complaint": "지속적 불안과 신체 증상",
            "present_illness": "범불안 양상, 자율신경 항진 증상 동반.",
            "symptoms": ["불안", "초조", "심계항진"],
            "onset": "약 3주 전",
            "recent_changes": "걱정 통제 어려움 심화",
            "triggers": ["불확실한 진로"],
            "sleep_appetite_activity": {
                "sleep": "입면 곤란",
                "appetite": "유지",
                "activity": "안절부절",
            },
            "psych_history": "없음",
            "medications": "없음",
            "documents_summary": [],
            "clinician_attention": ["GAD-7 중증 — 불안장애 평가 권장"],
            "evidence": [],
            "latency_ms": 0,
        },
    },
]


async def _make_clinician(db, settings: Settings, org_id: uuid.UUID) -> None:
    db.add(
        User(
            email=CLINICIAN_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD, settings),
            role="clinician",
            organization_id=org_id,
        )
    )


async def _make_persona(db, settings: Settings, p: dict) -> None:
    user = User(
        email=p["email"],
        password_hash=hash_password(DEMO_PASSWORD, settings),
        role="patient",
    )
    db.add(user)
    await db.flush()

    db.add(
        PatientProfile(
            user_id=user.id,
            name_encrypted=encrypt_str(
                p["name"], aad=_profile_aad(user.id, "name"), settings=settings
            ),
            birth_year=p["birth_year"],
            gender=p["gender"],
            phone_encrypted=encrypt_str(
                p["phone"], aad=_profile_aad(user.id, "phone"), settings=settings
            ),
            region=p["region"],
            emergency_contact_encrypted=encrypt_str(
                p["emergency"],
                aad=_profile_aad(user.id, "emergency_contact"),
                settings=settings,
            ),
        )
    )
    consent = ConsentSnapshot(
        user_id=user.id,
        tos=True,
        privacy=True,
        sensitive=True,
        risk_notification=True,
        voice=True,
        tos_version="2026-06-09",
        privacy_version="2026-06-09",
    )
    db.add(consent)
    await db.flush()

    sess = Session(
        patient_id=user.id,
        status="report_ready",
        submitted_at=datetime.now(UTC) - timedelta(hours=2),
    )
    db.add(sess)
    await db.flush()

    for text in p["messages"]:
        mid = uuid.uuid4()
        db.add(
            Message(
                id=mid,
                session_id=sess.id,
                role="user",
                content_encrypted=encrypt_str(
                    text, aad=_message_aad(sess.id, mid), settings=settings
                ),
                input_modality="text",
            )
        )

    for qtype, answers, sev_fn in (
        ("PHQ9", p["phq9"], _severity_phq9),
        ("GAD7", p["gad7"], _severity_gad7),
    ):
        total = sum(answers)
        db.add(
            QuestionnaireResult(
                session_id=sess.id,
                type=qtype,
                answers=answers,
                total_score=total,
                severity=sev_fn(total),
            )
        )

    if p["risk"] is not None:
        level, category = p["risk"]
        db.add(
            RiskEvent(
                patient_id=user.id,
                session_id=sess.id,
                level=level,
                category=category,
                status="detected",
                legal_basis="consent:risk_notification",
                consent_snapshot_id=consent.id,
            )
        )

    db.add(
        HandoffReport(
            session_id=sess.id,
            status="ready",
            content=p["narrative"],
            generated_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )


async def _main() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        existing = await db.execute(
            User.__table__.select().where(User.email == CLINICIAN_EMAIL)
        )
        if existing.first() is not None:
            print("demo already seeded — skipping")
            return

        org = Organization(name="데모 정신건강의학과", type="clinic")
        db.add(org)
        await db.flush()

        await _make_clinician(db, settings, org.id)
        for persona in PERSONAS:
            await _make_persona(db, settings, persona)

        await db.commit()
        print(
            f"seeded 1 clinician + {len(PERSONAS)} patients "
            f"(login password: {DEMO_PASSWORD})"
        )


if __name__ == "__main__":
    asyncio.run(_main())
