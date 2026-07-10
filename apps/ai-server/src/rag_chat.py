#!/usr/bin/env python3
"""RAG grounding 대화형 테스트 클라이언트 — 발화를 넣으면 grounding을 본다.

**in-process 스크립트다.** ADR-017/REV-013(2026-07-09): RAG HTTP API가 영구
retire되면서(`POST /ai/rag/grounding` 언마운트, `src/main.py`) 이 파일도 더 이상
HTTP 클라이언트가 아니다 — `src.rag.retrieval.retrieve_grounding()`을 로컬
DB 세션으로 직접 호출한다. `src/f2.py:176-180`의 Stage 1 호출이 이미 쓰는 것과
정확히 같은 in-process 패턴(`src.dependencies.get_sessionmaker()`)이다.

이제 서버 프로세스·포트·bearer 키가 필요 없다(HTTP round-trip 자체가 없다).
대신 f1.py/f2.py와 동일하게 **venv + `.env`(DATABASE_URL)** 가 필요하다 — 더는
"venv 없이 파일 하나만 복사해 실행"되는 도구가 아니다. 임베딩 조회 시
UPSTAGE_API_KEY도 필요.

ADR-013/VAL-005(2026-07-08) 이력: 과거엔 공인 IP:포트와 환자 UUID 4종이 파일에
하드코딩되어 있었다(엔드포인트가 무인증이던 시절엔 그 UUID가 사실상 접근
자격증명이었다). REV-013 §2: 라이브 HTTP 서피스 자체가 사라지면서 VAL-005는
구조적으로 해소됐다 — 아래 PERSONAS는 이제 로컬 DB의 임의 patient_id 조회
편의일 뿐, 원격 접근 자격증명이 아니다. 그럼에도 계속 명시 선택(:p VP-00N)만
지원한다(자동 기본값 없음 — 관행 유지).

실행: `python -m src.rag_chat`  (apps/ai-server에서, venv 필요)
env:
  NS_PATIENT_ID    환자 UUID 또는 VP-00N 별칭       (기본 없음 → my_past 미조회)
  NS_K             슬롯별 top-k 1~10                 (기본 3)

명령: 발화 입력 / ":p <uuid|VP-00N>" patient 변경 / ":k 5" k 변경 / ":q"/exit 종료.
DB 접속 정보(비밀번호 포함, `.env`의 DATABASE_URL)는 어디에도 출력/로그되지 않는다
— `get_sessionmaker()`가 내부에서 소비할 뿐, 이 파일은 DSN 문자열을 다루지 않는다.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any

# load_simulations로 적재된 VP 페르소나 별칭(결정론적 uuid5, 비밀 아님) — 편의 lookup일 뿐,
# 자동으로 쓰이는 기본값이 아니다(:p VP-004 처럼 명시적으로 선택해야 함, VAL-005 이력).
PERSONAS = {
    "VP-001": "adc981a1-07e6-5325-8cf0-e352ec2b45e5",
    "VP-002": "38066e4e-b2b5-5e06-bf38-4fbff4db3b76",
    "VP-003": "e75f5b7f-a126-50eb-8e9a-9a8860add584",
    "VP-004": "83ba5822-5088-5955-94a0-24ec569dc840",
}


def render(g: dict) -> str:
    lines: list[str] = []
    cases = g.get("similar_cases") or []
    lines.append(f"■ 유사사례(남의 사례) {len(cases)}건")
    for c in cases:
        lines.append(f"   [{c.get('score')}] {c.get('disease_class')} — {c.get('situation')}")

    past = g.get("my_past") or []
    lines.append(f"■ 내 과거 {len(past)}건")
    for p in past:
        lines.append(f"   [{p.get('score')}] {p.get('disease_class')} — {p.get('situation')}")
        meta = []
        if p.get("phq9_score") is not None:
            meta.append(f"PHQ-9={p.get('phq9_score')}")
        if p.get("gad7_score") is not None:
            meta.append(f"GAD-7={p.get('gad7_score')}")
        if p.get("flag_suicidal") is not None:
            meta.append(f"자살플래그={p.get('flag_suicidal')}")
        if meta:
            lines.append(f"        · {' / '.join(meta)}")
        for key, val in (p.get("slots") or {}).items():
            lines.append(f"        - {key}: {val}")

    know = g.get("knowledge") or []
    lines.append(f"■ 지식(QA) {len(know)}건")
    for q in know:
        lines.append(f"   [{q.get('score')}] Q: {q.get('question')}")
        lines.append(f"            A: {q.get('answer')}")

    lines.append(f"■ 감지된 증상: {g.get('mentioned_symptoms') or []}")
    fu = g.get("follow_up")
    if fu:
        lines.append(f"■ 후보질병: {fu.get('candidate_disease')}")
        lines.append(f"   미확인 증상(후속질문): {fu.get('follow_up_symptoms') or []}")
    else:
        lines.append("■ 후보질병: (없음)")
    return "\n".join(lines)


async def _query(utterance: str, patient_id: str | None, k: int) -> dict[str, Any]:
    """retrieve_grounding()을 로컬 DB 세션메이커로 직접 호출한다 (in-process, ADR-017).

    HTTP round-trip이 없다 — 실패 시 예외를 그대로 올려 REPL이 잡게 한다.
    """
    from uuid import UUID

    from src.dependencies import get_sessionmaker
    from src.rag.retrieval import retrieve_grounding

    pid: UUID | None = UUID(patient_id) if patient_id else None
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        return await retrieve_grounding(db, utterance, patient_id=pid, k=k)


def _parse_uuid(raw: str) -> str | None:
    """UUID 또는 'VP-00N' 별칭을 UUID 문자열로. 실패 시 None."""
    alias = PERSONAS.get((raw or "").strip().upper())
    if alias:
        return alias
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError):
        return None


async def _run() -> int:
    k = int(os.environ.get("NS_K", "3"))
    # VAL-005 이력: 하드코딩된 기본 환자 없음 — 명시적으로 지정해야만 my_past가 조회된다.
    pid = _parse_uuid(os.environ.get("NS_PATIENT_ID", "")) or None
    print(
        f"RAG in-process 테스트 클라이언트 (ADR-017/REV-013 — HTTP 아님)  k={k}  "
        f"patient_id={pid or '(미설정 → my_past 안 뜸)'}"
    )
    print("발화를 입력하세요. (:p <uuid|VP-00N> = 환자변경, :k N = k변경, :q/exit = 종료)\n")

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in (":q", ":quit", "exit", "quit"):
            break
        if line.startswith(":p"):
            parts = line.split()
            if len(parts) == 2 and _parse_uuid(parts[1]):
                pid = _parse_uuid(parts[1])
                print(f"(patient_id={pid})")
            else:
                print("사용법: :p <uuid> 또는 :p VP-004")
            continue
        if line.startswith(":k"):
            try:
                k = max(1, min(10, int(line.split()[1])))
                print(f"(k={k})")
            except (IndexError, ValueError):
                print("사용법: :k 5")
            continue

        try:
            data = await _query(line, pid, k)
        except Exception as exc:  # noqa: BLE001 — REPL: DB/임베딩 실패도 계속 진행하게 표시만
            print(f"[조회 실패] {exc}", file=sys.stderr)
            continue
        print("---")
        print(render(data))
        print()
    return 0


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
