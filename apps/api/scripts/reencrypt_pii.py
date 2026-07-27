"""ENCRYPTION_KEY 불일치로 복호화 실패하는 환자 PII를 현재 키로 재암호화한다.

배경: 하나의 공유 DB에 서로 다른 ENCRYPTION_KEY로 쓰인 행이 섞이면(예: dev api와
DGX api가 다른 키로 같은 DB에 기록), 각 인스턴스는 자기 키로 쓴 행만 복호화할 수
있고 나머지는 AES-GCM `InvalidTag`(복호화 실패)가 난다. 의료진 대시보드에서 일부
환자 이름이 "복호화 실패"로 뜨는 원인.

이 스크립트는 **실행 환경의 ENCRYPTION_KEY(= 정규 키)**를 타깃으로:
  1. 각 암호화 컬럼을 정규 키로 복호화 시도 → 성공하면 이미 정상, 건너뜀.
  2. 실패하면 `LEGACY_ENCRYPTION_KEYS`(env, base64-urlsafe 32B, 쉼표구분)의 각 키로
     복호화 시도 → 성공한 키로 평문을 얻어 **정규 키로 재암호화**해 UPDATE 대상에 담음.
  3. 어떤 키로도 못 읽으면 unrecoverable로 보고(원본 키 소실 — 삭제/재생성만 가능).

대상: patient_profiles(name/phone/emergency_contact), messages(content).
키는 인자·git에 남기지 않는다 — 반드시 env로 주입한다.

    # DGX api 컨테이너 안(정규 키 = 컨테이너 env)에서:
    LEGACY_ENCRYPTION_KEYS="<이 데이터를 쓴 다른 키(base64)>" \
      python -m scripts.reencrypt_pii            # dry-run(보고만)
    LEGACY_ENCRYPTION_KEYS="..." python -m scripts.reencrypt_pii --apply   # 실제 UPDATE
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from src.core.encryption import NONCE_BYTES, encrypt_bytes
from src.db import SessionLocal
from src.models.session import Message
from src.models.patient_profile import PatientProfile


def _profile_aad(user_id: uuid.UUID, column: str) -> bytes:
    return f"patient_profiles.{column}:{user_id}".encode()


def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


def _load_legacy_keys() -> list[bytes]:
    raw = os.getenv("LEGACY_ENCRYPTION_KEYS", "").strip()
    keys: list[bytes] = []
    for tok in (t.strip() for t in raw.split(",") if t.strip()):
        k = base64.urlsafe_b64decode(tok + "===")
        if len(k) != 32:
            raise SystemExit(f"legacy key decoded to {len(k)} bytes (need 32): {tok[:8]}…")
        keys.append(k)
    return keys


def _try_decrypt_legacy(blob: bytes, aad: bytes, legacy: list[bytes]) -> bytes | None:
    """레거시 키들로 복호화 시도. 성공하면 평문 bytes, 전부 실패하면 None."""
    if len(blob) <= NONCE_BYTES:
        return None
    nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    for k in legacy:
        try:
            return AESGCM(k).decrypt(nonce, ct, aad)
        except Exception:
            continue
    return None


def _canonical_ok(blob: bytes, aad: bytes) -> bool:
    """정규 키(현재 settings)로 복호화되면 True."""
    from src.core.encryption import decrypt_bytes

    try:
        decrypt_bytes(blob, aad=aad)
        return True
    except Exception:
        return False


async def main(apply: bool) -> None:
    legacy = _load_legacy_keys()
    if not legacy:
        print("LEGACY_ENCRYPTION_KEYS 가 비어 있습니다 — 재암호화할 원본 키를 env로 주입하세요.")
        return
    print(f"legacy 키 {len(legacy)}개 로드. mode={'APPLY' if apply else 'DRY-RUN'}")

    converted = already = unrecoverable = 0
    async with SessionLocal() as db:
        # ── patient_profiles ──
        profs = (await db.execute(select(PatientProfile))).scalars().all()
        for p in profs:
            for col in ("name", "phone", "emergency_contact"):
                blob = getattr(p, f"{col}_encrypted")
                if blob is None:
                    continue
                aad = _profile_aad(p.user_id, col)
                if _canonical_ok(blob, aad):
                    already += 1
                    continue
                pt = _try_decrypt_legacy(blob, aad, legacy)
                if pt is None:
                    unrecoverable += 1
                    print(f"  UNRECOVERABLE profile {p.user_id} .{col}")
                    continue
                if apply:
                    setattr(p, f"{col}_encrypted", encrypt_bytes(pt, aad=aad))
                converted += 1

        # ── messages.content ──
        msgs = (await db.execute(select(Message))).scalars().all()
        for m in msgs:
            blob = m.content_encrypted
            if blob is None:
                continue
            aad = _message_aad(m.session_id, m.id)
            if _canonical_ok(blob, aad):
                already += 1
                continue
            pt = _try_decrypt_legacy(blob, aad, legacy)
            if pt is None:
                unrecoverable += 1
                continue
            if apply:
                m.content_encrypted = encrypt_bytes(pt, aad=aad)
            converted += 1

        if apply:
            await db.commit()

    print(
        f"\n결과: 이미정상 {already} · 재암호화{'(적용)' if apply else '(예정)'} {converted} "
        f"· 복구불가 {unrecoverable}"
    )
    if not apply and converted:
        print("→ --apply 를 붙여 실제 UPDATE 하세요.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv[1:]))
