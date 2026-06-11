"""AES-256-GCM column encryption.

PRD §4.5.2: AES-256 at-rest for 이름/연락처/대화/문서.

Format on disk (BYTEA):
    | 12-byte nonce | ciphertext + 16-byte GCM tag |

Key management:
- Demo: 32-byte key from `ENCRYPTION_KEY` env, base64-urlsafe-encoded.
  Short / non-base64 inputs are REJECTED — no silent derivation (M-2).
- Phase 2: KMS-backed key rotation (per-record `key_version`).

Associated Authenticated Data (AAD):
- All callers SHOULD pass `aad` binding the blob to its `(table, column, owner_id)`
  to prevent cross-record swaps. Defaults to `None` for backwards compat — log
  caller-less use as a Phase 2 hardening (M-10).
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.config import Settings, get_settings

NONCE_BYTES = 12
KEY_BYTES = 32


def _decode_key(encoded: str) -> bytes:
    """Strict base64-urlsafe decode → exactly 32 bytes. No fallback."""
    encoded = encoded.strip()
    try:
        raw = base64.urlsafe_b64decode(encoded + "===")
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError(
            "ENCRYPTION_KEY must be base64-urlsafe(32 bytes). "
            "Generate with: python -c "
            "\"import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
        ) from exc
    if len(raw) != KEY_BYTES:
        raise ValueError(
            f"ENCRYPTION_KEY decoded to {len(raw)} bytes — must be exactly {KEY_BYTES}."
        )
    return raw


def _cipher(settings: Settings | None = None) -> AESGCM:
    settings = settings or get_settings()
    return AESGCM(_decode_key(settings.encryption_key.get_secret_value()))


def encrypt_bytes(
    plaintext: bytes | str,
    *,
    aad: bytes | None = None,
    settings: Settings | None = None,
) -> bytes:
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    nonce = os.urandom(NONCE_BYTES)
    blob = _cipher(settings).encrypt(nonce, plaintext, associated_data=aad)
    return nonce + blob


def decrypt_bytes(
    blob: bytes,
    *,
    aad: bytes | None = None,
    settings: Settings | None = None,
) -> bytes:
    if len(blob) <= NONCE_BYTES:
        raise ValueError("ciphertext too short")
    nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    return _cipher(settings).decrypt(nonce, ct, associated_data=aad)


def encrypt_str(
    plaintext: str, *, aad: bytes | None = None, settings: Settings | None = None
) -> bytes:
    return encrypt_bytes(plaintext, aad=aad, settings=settings)


def decrypt_str(
    blob: bytes, *, aad: bytes | None = None, settings: Settings | None = None
) -> str:
    return decrypt_bytes(blob, aad=aad, settings=settings).decode("utf-8")
