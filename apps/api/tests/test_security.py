"""Unit tests for security primitives — no DB required."""

import pytest

from src.core.config import Settings
from src.core.encryption import decrypt_str, encrypt_str
from src.core.security import (
    PasswordPolicyError,
    TokenError,
    create_token,
    decode_token,
    hash_password,
    validate_password_policy,
    verify_password,
)


@pytest.fixture
def fast_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        jwt_secret_key="unit-test-jwt-secret-32bytes-padding____",
        encryption_key="ZGV2LTMyLWJ5dGVzLW9ubHktRE8tTk9ULVVTRS1GT1I=",
        argon2_memory_cost_kib=8,
        argon2_time_cost=1,
        argon2_parallelism=1,
    )


# ---------- Password policy ----------


def test_password_policy_passes_strong(fast_settings):
    # Must not raise
    validate_password_policy("Strong-Password-2026!", fast_settings)


@pytest.mark.parametrize(
    "weak,expected_reason",
    [
        ("short", "min_length_12"),
        ("alllowercase!1aa", "uppercase_required"),
        ("ALLUPPERCASE!1AA", "lowercase_required"),
        ("NoDigitInThis!aaA", "digit_required"),
        ("NoSymbol123aaaaA", "symbol_required"),
    ],
)
def test_password_policy_rejects(weak, expected_reason, fast_settings):
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy(weak, fast_settings)
    assert expected_reason in exc.value.reasons


# ---------- Argon2id ----------


def test_argon2id_hash_verify_roundtrip(fast_settings):
    h = hash_password("Hunter2-Strong!Password", fast_settings)
    assert h.startswith("$argon2id$")
    assert verify_password("Hunter2-Strong!Password", h, fast_settings) is True
    assert verify_password("WrongPassword!2026", h, fast_settings) is False


def test_argon2id_different_hashes_for_same_password(fast_settings):
    a = hash_password("Same-Password-Twice!1", fast_settings)
    b = hash_password("Same-Password-Twice!1", fast_settings)
    assert a != b  # random salt
    assert verify_password("Same-Password-Twice!1", a, fast_settings)
    assert verify_password("Same-Password-Twice!1", b, fast_settings)


# ---------- JWT ----------


def test_jwt_access_roundtrip(fast_settings):
    token = create_token("user-123", "access", role="patient", settings=fast_settings)
    claims = decode_token(token, expected_type="access", settings=fast_settings)
    assert claims["sub"] == "user-123"
    assert claims["role"] == "patient"
    assert claims["typ"] == "access"


def test_jwt_refresh_typ_enforced(fast_settings):
    token = create_token("user-123", "refresh", settings=fast_settings)
    # Passes when expected_type matches
    decode_token(token, expected_type="refresh", settings=fast_settings)
    # Fails when expected_type mismatches
    with pytest.raises(TokenError, match="TOKEN_TYPE_MISMATCH"):
        decode_token(token, expected_type="access", settings=fast_settings)


def test_jwt_includes_iss_aud_jti(fast_settings):
    """C-4 hardening: tokens must carry iss/aud/jti."""
    token = create_token("user-123", "access", settings=fast_settings)
    claims = decode_token(token, expected_type="access", settings=fast_settings)
    assert claims["iss"] == fast_settings.jwt_issuer
    assert claims["aud"] == fast_settings.jwt_audience
    assert claims["jti"]  # non-empty random id
    # Each token gets a fresh jti
    token2 = create_token("user-123", "access", settings=fast_settings)
    claims2 = decode_token(token2, expected_type="access", settings=fast_settings)
    assert claims["jti"] != claims2["jti"]


def test_password_policy_accepts_unicode_letters(fast_settings):
    """M-3: NIST SP 800-63B / PRD §4.5.2 — unicode letters must count."""
    # Korean uppercase doesn't exist, so we use latin upper + Korean letter + symbol + digit
    validate_password_policy("Aa비밀번호1!aaaaaa", fast_settings)


def test_password_policy_rejects_oversized(fast_settings):
    from src.core.security import PasswordPolicyError

    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("Aa1!" + "a" * 300, fast_settings)
    assert any(r.startswith("max_length_") for r in exc.value.reasons)


def test_jwt_tampered_signature_rejected(fast_settings):
    token = create_token("user-123", "access", settings=fast_settings)
    # Tamper a char inside the signature segment so the change cannot be
    # absorbed by base64 padding bits (the very last char of a 32-byte HS256
    # signature carries only 4 payload bits + 2 padding bits, which can leave
    # the decoded bytes unchanged on some single-char flips).
    last_dot = token.rfind(".")
    sig = token[last_dot + 1 :]
    idx = len(sig) // 2  # middle of signature
    flipped_char = "A" if sig[idx] != "A" else "B"
    tampered = token[: last_dot + 1] + sig[:idx] + flipped_char + sig[idx + 1 :]
    with pytest.raises(TokenError):
        decode_token(tampered, settings=fast_settings)


# ---------- AES-256-GCM ----------


def test_aes_gcm_roundtrip(fast_settings):
    plaintext = "홍길동 010-1234-5678"
    ct = encrypt_str(plaintext, settings=fast_settings)
    assert ct != plaintext.encode()
    assert decrypt_str(ct, settings=fast_settings) == plaintext


def test_aes_gcm_nonce_uniqueness(fast_settings):
    a = encrypt_str("same", settings=fast_settings)
    b = encrypt_str("same", settings=fast_settings)
    assert a != b  # nonce differs each call
    assert decrypt_str(a, settings=fast_settings) == "same"
    assert decrypt_str(b, settings=fast_settings) == "same"
