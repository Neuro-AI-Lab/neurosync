"""Auth router — PRD §5.1 /auth/register, /auth/login, /auth/refresh.

Implements:
- FR-001 환자 회원가입 + 4개 동의 분리
- FR-002 프로필 입력 (이름/연령/성별/연락처/지역/비상연락처)
- FR-015 의료진 로그인 (역할 검증)
- FR-026 위험 통보 동의 (옵트인/아웃 양자택일)

Demo OUT (Phase 2):
- FR-027 만 14세 미만 법정대리인 verification (스키마는 받지만 verification은 Phase 2)
- FR-031 idle 15분 세션 타임아웃, 2FA
- FR-030 audit hash chain + UPDATE/DELETE 트리거
- Refresh token revocation (jti is in tokens for forward compat — C-4)

Design notes:
- `birth_year` is intentionally plaintext to feed the Postgres GENERATED column
  `patient_profiles.is_minor`. This trades column-level confidentiality for
  query-time enforcement of FR-027. Quasi-identifier risk is acknowledged;
  reconsider in Phase 2 with KMS + app-managed `is_minor` if year-precise
  analytics are not required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.encryption import encrypt_str
from src.core.security import (
    PasswordPolicyError,
    TokenError,
    create_token,
    decode_token,
    hash_password,
    validate_password_policy,
    verify_password,
)
from src.db import get_session
from src.models.audit_log import AuditLog
from src.models.consent import ConsentSnapshot
from src.models.patient_profile import PatientProfile
from src.models.user import User
from src.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SuccessResponse,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Consent document versions — bumped when wording changes (FR-001 audit ability).
TOS_VERSION = "2026-06-09"
PRIVACY_VERSION = "2026-06-09"

# C-3: pre-computed dummy hash used to keep /login response time constant
# whether or not the user exists. Lazily built on first use with the same
# Settings the request would use.
_DUMMY_HASH_CACHE: dict[int, str] = {}


def _dummy_hash(settings: Settings) -> str:
    cache_key = id(settings)
    if cache_key not in _DUMMY_HASH_CACHE:
        _DUMMY_HASH_CACHE[cache_key] = hash_password(
            "dummy-password-not-a-secret", settings
        )
    return _DUMMY_HASH_CACHE[cache_key]


def _raise_api_error(
    status_code: int, code: str, message: str, details: list | None = None
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or []},
    )


def _is_minor(birth_year: int, settings: Settings) -> bool:
    """C-5: UTC clock to align with Postgres CURRENT_DATE (UTC)."""
    return (datetime.now(tz=UTC).year - birth_year) < settings.minor_age_cutoff


def _check_required_consents(payload: RegisterRequest) -> None:
    c = payload.consents
    missing = [
        field
        for field, ok in (
            ("tos", c.tos),
            ("privacy", c.privacy),
            ("sensitive", c.sensitive),
        )
        if not ok
    ]
    if missing:
        _raise_api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "CONSENT_REQUIRED",
            "필수 동의가 누락되었습니다.",
            details=[{"field": f, "message": "required"} for f in missing],
        )


def _check_guardian(payload: RegisterRequest, settings: Settings) -> None:
    if not _is_minor(payload.birth_year, settings):
        return
    if payload.guardian_consent is None:
        _raise_api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "GUARDIAN_CONSENT_REQUIRED",
            "만 14세 미만은 법정대리인 동의가 필요합니다.",
        )


async def _write_audit(
    session: AsyncSession,
    *,
    actor_id,
    actor_role: str,
    action: str,
    request: Request,
    metadata: dict | None = None,
    resource_type: str | None = None,
    resource_id=None,
) -> None:
    """Minimal audit log writer — FR-023. Hash chain is Phase 2 (FR-030)."""
    entry = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        audit_metadata=metadata,
    )
    session.add(entry)


def _profile_aad(user_id: UUID, column: str) -> bytes:
    """Bind each encrypted column to its owner so cross-record swaps fail (M-10)."""
    return f"patient_profiles.{column}:{user_id}".encode()


def _token_pair(user: User, settings: Settings) -> TokenPair:
    return TokenPair(
        user_id=user.id,
        access_token=create_token(user.id, "access", role=user.role, settings=settings),
        refresh_token=create_token(user.id, "refresh", role=user.role, settings=settings),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessResponse:
    # 1) Password policy
    try:
        validate_password_policy(payload.password, settings)
    except PasswordPolicyError as exc:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "WEAK_PASSWORD",
            "비밀번호 정책을 만족하지 않습니다.",
            details=[{"reason": r} for r in exc.reasons],
        )

    # 2) Consent enforcement (FR-001/026/027)
    _check_required_consents(payload)
    _check_guardian(payload, settings)

    # 3) Email uniqueness — fast-path check. Race-condition fallback at flush().
    existing = await session.execute(select(User.id).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        _raise_api_error(
            status.HTTP_409_CONFLICT,
            "EMAIL_EXISTS",
            "이미 가입된 이메일이에요.",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password, settings),
        role="patient",
    )
    session.add(user)
    try:
        await session.flush()  # populate user.id + catch race-condition dup
    except IntegrityError as exc:
        await session.rollback()
        msg = str(getattr(exc, "orig", exc)).lower()
        if "email" in msg and "unique" in msg or "users_email" in msg:
            _raise_api_error(
                status.HTTP_409_CONFLICT,
                "EMAIL_EXISTS",
                "이미 가입된 이메일이에요.",
            )
        raise

    profile = PatientProfile(
        user_id=user.id,
        name_encrypted=encrypt_str(
            payload.name, aad=_profile_aad(user.id, "name"), settings=settings
        ),
        birth_year=payload.birth_year,
        gender=payload.gender,
        phone_encrypted=encrypt_str(
            payload.phone, aad=_profile_aad(user.id, "phone"), settings=settings
        ),
        region=payload.region,
        emergency_contact_encrypted=encrypt_str(
            payload.emergency_contact,
            aad=_profile_aad(user.id, "emergency_contact"),
            settings=settings,
        ),
        target_hospital_id=payload.target_hospital_id,
    )
    session.add(profile)

    snapshot = ConsentSnapshot(
        user_id=user.id,
        tos=payload.consents.tos,
        privacy=payload.consents.privacy,
        sensitive=payload.consents.sensitive,
        risk_notification=payload.consents.risk_notification,
        voice=bool(payload.consents.voice),  # FR-034 optional opt-in at signup
        guardian_consent=(
            payload.guardian_consent.model_dump(by_alias=True, mode="json")
            if payload.guardian_consent
            else None
        ),
        tos_version=TOS_VERSION,
        privacy_version=PRIVACY_VERSION,
        collected_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    session.add(snapshot)

    await _write_audit(
        session,
        actor_id=user.id,
        actor_role="patient",
        action="auth.register",
        request=request,
        resource_type="user",
        resource_id=user.id,
        metadata={"birth_year": payload.birth_year},
    )

    await session.commit()

    return SuccessResponse(data=_token_pair(user, settings).model_dump(by_alias=True))


@router.post("/login", response_model=SuccessResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessResponse:
    result = await session.execute(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # C-3: run Argon2 even when user is absent so response time doesn't reveal
    # whether the email exists. Always verify exactly once per request.
    if user is None:
        verify_password("dummy-password-not-a-secret", _dummy_hash(settings), settings)
        password_ok = False
    else:
        password_ok = verify_password(payload.password, user.password_hash, settings)

    if user is None or not password_ok:
        _raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "이메일 또는 비밀번호가 일치하지 않아요.",
        )

    if user.role != payload.role:
        _raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "ROLE_MISMATCH",
            "이 계정으로 해당 영역에 접근할 수 없습니다.",
        )

    await _write_audit(
        session,
        actor_id=user.id,
        actor_role=user.role,
        action="auth.login",
        request=request,
        resource_type="user",
        resource_id=user.id,
    )
    await session.commit()

    return SuccessResponse(data=_token_pair(user, settings).model_dump(by_alias=True))


@router.post("/refresh", response_model=SuccessResponse)
async def refresh_tokens(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessResponse:
    try:
        claims = decode_token(
            payload.refresh_token, expected_type="refresh", settings=settings
        )
    except TokenError as exc:
        _raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            exc.code.value,
            "리프레시 토큰이 유효하지 않아요.",
        )

    # M-9: validate sub is a UUID before hitting the DB
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError):
        _raise_api_error(
            status.HTTP_401_UNAUTHORIZED, "TOKEN_INVALID", "토큰이 유효하지 않아요."
        )

    result = await session.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        _raise_api_error(
            status.HTTP_401_UNAUTHORIZED, "USER_NOT_FOUND", "사용자를 찾을 수 없어요."
        )

    access = create_token(user.id, "access", role=user.role, settings=settings)
    return SuccessResponse(
        data={
            "accessToken": access,
            "expiresIn": settings.access_token_expire_minutes * 60,
        }
    )
