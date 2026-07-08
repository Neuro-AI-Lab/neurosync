"""src.rag.crypto — AES-GCM round-trip + decrypt-absent fallback (S2, S3).

Mock/fixture-based only, no DB, no network.
"""

from __future__ import annotations

import base64
import os

import pytest

from src.rag import crypto


def _make_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


class TestEncryptDecryptRoundtrip:
    def test_roundtrip_no_aad(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        blob = crypto.encrypt_str("안녕하세요")
        assert crypto.decrypt_str(blob) == "안녕하세요"

    def test_roundtrip_with_matching_aad(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        aad = crypto.session_insights_aad("sess-1", "situation")
        blob = crypto.encrypt_str("불안감과 수면 문제", aad=aad)
        assert crypto.decrypt_str(blob, aad=aad) == "불안감과 수면 문제"

    def test_wrong_aad_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        blob = crypto.encrypt_str("secret", aad=b"aad-a")
        with pytest.raises(Exception):  # noqa: B017 — cryptography raises InvalidTag
            crypto.decrypt_str(blob, aad=b"aad-b")

    def test_wrong_key_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        blob = crypto.encrypt_str("secret")
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())  # rotate to a different key
        with pytest.raises(Exception):  # noqa: B017
            crypto.decrypt_str(blob)

    def test_too_short_blob_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        with pytest.raises(ValueError):
            crypto.decrypt_str(b"short")


class TestDecryptAbsentKeyFallback:
    """S2/ADR-013: ENCRYPTION_KEY absent must fail loudly (RuntimeError), never
    silently return plaintext-looking garbage — the caller (retrieval._dec)
    is what turns this into a safe field-exclusion."""

    def test_decrypt_raises_when_key_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        with pytest.raises(RuntimeError):
            crypto.decrypt_str(b"x" * 20)

    def test_encrypt_also_raises_when_key_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        with pytest.raises(RuntimeError):
            crypto.encrypt_str("secret")


class TestAadHelpers:
    def test_session_insights_aad_format(self) -> None:
        assert (
            crypto.session_insights_aad("sess-1", "situation")
            == b"session_insights.situation:sess-1"
        )

    def test_session_insights_aad_matches_profile_aad_convention(self) -> None:
        assert crypto.profile_aad("u1", "name") == b"patient_profiles.name:u1"
        assert crypto.session_insights_aad("s1", "situation") == b"session_insights.situation:s1"
