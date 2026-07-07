"""컬럼 암호화/해시 — ai-server 로더 전용 (오프라인).

apps/api `src/core/encryption.py`(AES-256-GCM)와 **동일 포맷·동일 AAD**를 재현한다.
api가 넣은 값을 앱이 읽는 것과 마찬가지로, 여기서 넣은 message/name도 앱이 복호화한다.
→ 반드시 api와 같은 ENCRYPTION_KEY(base64-urlsafe 32B)를 써야 한다.

on-disk 포맷: | 12B nonce | ciphertext + 16B GCM tag |  (api와 동일)

pydantic-settings/src.core 의존 없이 os.getenv만 읽어 이식성 유지.
"""

from __future__ import annotations

import base64
import os

from argon2 import PasswordHasher
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32

_ph = PasswordHasher()


def _key() -> bytes:
    """ENCRYPTION_KEY(base64-urlsafe) → 정확히 32바이트. api _decode_key와 동일 규칙."""
    encoded = os.getenv("ENCRYPTION_KEY", "").strip()
    if not encoded:
        raise RuntimeError("ENCRYPTION_KEY 미설정 — api와 동일 값을 ai-server/.env에 넣어야 함")
    raw = base64.urlsafe_b64decode(encoded + "===")
    if len(raw) != KEY_BYTES:
        raise ValueError(f"ENCRYPTION_KEY decoded to {len(raw)} bytes — must be {KEY_BYTES}.")
    return raw


def encrypt_str(plaintext: str, *, aad: bytes | None = None) -> bytes:
    """api encrypt_str와 바이트 호환. nonce(12) + AESGCM(ct+tag)."""
    nonce = os.urandom(NONCE_BYTES)
    blob = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return nonce + blob


def hash_password(plaintext: str) -> str:
    """argon2 해시 (api security.hash_password와 같은 계열, 기본 파라미터).
    argon2 해시는 파라미터를 자체 기술하므로 앱의 verify와 호환."""
    return _ph.hash(plaintext)


# ── AAD 헬퍼 (api seed_demo와 동일 포맷) ────────────────────────────────
def profile_aad(user_id: str, column: str) -> bytes:
    return f"patient_profiles.{column}:{user_id}".encode()


def message_aad(session_id: str, message_id: str) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()
