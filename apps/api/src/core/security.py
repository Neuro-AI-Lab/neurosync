"""Password hashing (Argon2id) + JWT encode/decode.

PRD §4.5.2:
- 비밀번호 해시: Argon2id (memory_cost ≥ 64MB, iterations ≥ 3)
- 비밀번호 정책: 최소 12자, 영문 대소문자+숫자+특수문자 조합 (NIST SP 800-63B-aware unicode)

JWT hardening (C-4):
- `iss` / `aud` enforced — no cross-service token reuse
- `jti` (uuid4) added — enables Phase 2 revocation table without breaking change
- `typ: access|refresh` discriminator
"""

from __future__ import annotations

import unicodedata
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from src.core.config import Settings, get_settings

TokenType = Literal["access", "refresh"]


class TokenErrorCode(StrEnum):
    EXPIRED = "TOKEN_EXPIRED"
    INVALID = "TOKEN_INVALID"
    TYPE_MISMATCH = "TOKEN_TYPE_MISMATCH"


def _build_hasher(settings: Settings) -> PasswordHasher:
    return PasswordHasher(
        memory_cost=settings.argon2_memory_cost_kib,
        time_cost=settings.argon2_time_cost,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(plaintext: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _build_hasher(settings).hash(plaintext)


def verify_password(plaintext: str, hashed: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    try:
        _build_hasher(settings).verify(hashed, plaintext)
        return True
    except VerifyMismatchError:
        return False


# Password policy validator — surfaces structured reasons for WEAK_PASSWORD response.
class PasswordPolicyError(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("Password does not meet policy")
        self.reasons = reasons


def validate_password_policy(plaintext: str, settings: Settings | None = None) -> None:
    """PRD §4.5.2 password policy — unicode-aware per NIST SP 800-63B 2024."""
    settings = settings or get_settings()
    # NFKC normalize so visually-equivalent characters compare equal
    # (e.g., U+FF21 'Ａ' counts as A).
    s = unicodedata.normalize("NFKC", plaintext)

    reasons: list[str] = []
    if len(s) < settings.password_min_length:
        reasons.append(f"min_length_{settings.password_min_length}")
    # Cap input length to bound hash time (DoS guard).
    if len(s) > settings.password_max_length:
        reasons.append(f"max_length_{settings.password_max_length}")
    if not any(c.isupper() for c in s):
        reasons.append("uppercase_required")
    if not any(c.islower() for c in s):
        reasons.append("lowercase_required")
    if not any(c.isdigit() for c in s):
        reasons.append("digit_required")
    if not any((not c.isalnum()) and (not c.isspace()) for c in s):
        reasons.append("symbol_required")
    if reasons:
        raise PasswordPolicyError(reasons)


# ----- JWT -----


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def create_token(
    subject: str | UUID,
    token_type: TokenType,
    *,
    role: str | None = None,
    extra_claims: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    now = _now_utc()
    if token_type == "access":
        exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        exp = now + timedelta(days=settings.refresh_token_expire_days)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": _uuid.uuid4().hex,
    }
    if role is not None:
        payload["role"] = role
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


class TokenError(ValueError):
    """Carries a stable TokenErrorCode for API contract."""

    def __init__(self, code: TokenErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def decode_token(
    token: str,
    *,
    expected_type: TokenType | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "typ", "iss", "aud", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError(TokenErrorCode.EXPIRED) from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(TokenErrorCode.INVALID) from exc

    if expected_type is not None and payload.get("typ") != expected_type:
        raise TokenError(TokenErrorCode.TYPE_MISMATCH)
    return payload
