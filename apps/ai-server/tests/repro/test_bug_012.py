"""BUG-012 repro: `load_simulations.py` writes `situation_encrypted` as raw
plaintext UTF-8 bytes, but `retrieval._dec()` (S2, ADR-013) now genuinely
decrypts that column — so every VP-001~004 `my_past.situation` value loaded
by this tool comes back as `None`, silently, post-S2.

Flagged by developer at handoff (F2/ADR-013 mission) as a pre-existing,
untouched-by-this-PR loader defect surfaced by the S2 fix (before S2,
`_dec` did a raw `utf-8 decode(errors='ignore')`, so this loader's genuinely
plaintext bytes happened to decode back to readable text — masking the
column-name/encryption mismatch entirely). qa adjudication: genuine defect,
not a false positive of the S2 fix — `situation_encrypted` is the ONLY column
this loader leaves unencrypted; `name` and `message.content` in the SAME
file/function ARE properly encrypted via `crypto.encrypt_str` (see
`src/rag/tooling/load_simulations.py` lines ~144, ~176 vs ~202).

Root cause: `src/rag/tooling/load_simulations.py:202` —
    situation.encode("utf-8"),  # 평문바이트 (retrieval._dec가 그대로 decode)
— written directly as plaintext bytes instead of
`crypto.encrypt_str(situation, aad=crypto.session_insights_aad(...))`.

This repro isolates the defect at the code level (no DB): it reproduces the
exact byte-write pattern from the loader line above and feeds it through the
real `src.rag.retrieval._dec` used by `retrieve_grounding`, with a real
ENCRYPTION_KEY configured (so this is not the already-covered "key
missing/malformed ciphertext" case in `tests/rag/test_retrieval.py` — this is
specifically "loader wrote plaintext where the schema/decrypt path expects
ciphertext").

Impact: `rag.session_insights.situation` (`my_past[].situation` in the
`/ai/rag/grounding` response, and — per REV-006 issue #7, if F2 Stage 1 is
ever extended to `session_insights` — an F2 evidence source) is unusable for
any VP-001~004 data loaded via this tool until the loader is fixed to encrypt
`situation` the same way it already encrypts `name`/message content.
"""

from __future__ import annotations

import base64
import os

import pytest

from src.rag import crypto
from src.rag.retrieval import _dec

_SITUATION = "불안감과 수면 문제로 상담을 시작한 사례입니다."


def _make_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


class TestBug012LoaderPlaintextMismatch:
    def test_loader_written_plaintext_bytes_fail_to_decrypt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-012: reproduces `load_simulations.py:202`'s exact write —
        `situation.encode("utf-8")` — stored where `_dec` expects an
        AES-GCM blob (nonce + ciphertext + tag). Documents the bug (passes
        pre-fix); invert once the loader encrypts `situation` for real."""
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        aad = crypto.session_insights_aad("sess-bug012", "situation")

        # Exact write pattern from load_simulations.py line 202.
        loader_written_bytes = _SITUATION.encode("utf-8")

        result = _dec(loader_written_bytes, aad=aad)

        # Bug: the real data is lost — not decrypted, not surfaced, just gone.
        assert result is None

    def test_properly_encrypted_situation_would_roundtrip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Contrast case: if the loader used `crypto.encrypt_str` for
        `situation` (the same primitive it already uses for `name`/message
        content in the same file), `_dec` recovers it correctly — proving the
        defect is the loader's write path, not `_dec`/S2 itself."""
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        aad = crypto.session_insights_aad("sess-bug012", "situation")

        correctly_encrypted_bytes = crypto.encrypt_str(_SITUATION, aad=aad)

        result = _dec(correctly_encrypted_bytes, aad=aad)

        assert result == _SITUATION
