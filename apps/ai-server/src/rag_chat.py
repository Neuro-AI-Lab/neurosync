#!/usr/bin/env python3
"""RAG grounding 대화형 테스트 클라이언트 — 발화를 ai-server로 보내 grounding을 본다.

**HTTP 클라이언트**다. ai-server의 POST /ai/rag/grounding 을 때린다. DB·키·의존성이
전혀 필요 없어 표준 라이브러리(urllib)만 쓰므로, venv 없이 노트북 어디서든 파일 하나만
복사해 `python rag_chat.py` 로 실행된다. (RAG 로직 자체는 ai-server에서 돈다.)

ADR-013/VAL-005(2026-07-08): 이전에는 공인 IP:포트와 환자 UUID 4종이 파일에 하드코딩되어
있었다 — 엔드포인트가 무인증이던 시절엔 그 UUID가 사실상 접근 자격증명이었다. 이제 서버가
`NS_RAG_API_KEY` bearer 인증을 요구하므로(fail-closed 기본값 — 미설정 시 503), 하드코딩된
공인 접속 정보는 더 이상 이 파일에 없다. URL/patient/API 키는 모두 env 또는 REPL 명령으로
넘긴다 — 아무 것도 지정하지 않으면 로컬(localhost)로만 접속을 시도하고 my_past는 조회하지
않는다(patient_id 미지정).

실행: `python rag_chat.py`  (또는 apps/ai-server에서 `python -m src.rag_chat`)
env:
  NS_RAG_URL       ai-server 베이스 URL (기본 http://localhost:8001 — 원격 접속은 명시 지정)
  NS_RAG_API_KEY   서버의 NS_RAG_API_KEY와 동일한 값 (있으면 Authorization: Bearer 헤더로 전송)
  NS_PATIENT_ID    환자 UUID 또는 VP-00N 별칭       (기본 없음 → my_past 미조회)
  NS_K             슬롯별 top-k 1~10                 (기본 3)

명령: 발화 입력 / ":p <uuid|VP-00N>" patient 변경 / ":k 5" k 변경 / ":q"/exit 종료.
비밀 값(NS_RAG_API_KEY)은 어디에도 출력하지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

# 안전한 로컬 기본값만 — 원격/공인 주소는 반드시 NS_RAG_URL로 명시 지정한다.
DEFAULT_URL = "http://localhost:8001"

# load_simulations로 적재된 VP 페르소나 별칭(결정론적 uuid5, 비밀 아님) — 편의 lookup일 뿐,
# 자동으로 쓰이는 기본값이 아니다(:p VP-004 처럼 명시적으로 선택해야 함, VAL-005).
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


def _query(base_url: str, utterance: str, patient_id: str | None, k: int) -> dict:
    """POST /ai/rag/grounding — 실패 시 예외를 올려 REPL이 잡게 한다.

    NS_RAG_API_KEY가 설정되어 있으면 Authorization: Bearer 헤더로 전송한다
    (ADR-013). 키 값 자체는 절대 로그/출력하지 않는다.
    """
    body = json.dumps(
        {"utterance": utterance, "patient_id": patient_id, "k": k}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("NS_RAG_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/ai/rag/grounding",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — 신뢰된 내부 URL
        return json.loads(resp.read().decode("utf-8"))


def _parse_uuid(raw: str) -> str | None:
    """UUID 또는 'VP-00N' 별칭을 UUID 문자열로. 실패 시 None."""
    alias = PERSONAS.get((raw or "").strip().upper())
    if alias:
        return alias
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError):
        return None


def main() -> int:
    base_url = os.environ.get("NS_RAG_URL", DEFAULT_URL)
    k = int(os.environ.get("NS_K", "3"))
    # VAL-005: 하드코딩된 기본 환자 없음 — 명시적으로 지정해야만 my_past가 조회된다.
    pid = _parse_uuid(os.environ.get("NS_PATIENT_ID", "")) or None
    has_key = bool(os.environ.get("NS_RAG_API_KEY", "").strip())
    auth_note = (
        "Bearer 헤더 전송" if has_key
        else "(NS_RAG_API_KEY 미설정 — 서버가 503/401 반환 가능)"
    )
    print(f"RAG 테스트 클라이언트  server={base_url}  k={k}  "
          f"patient_id={pid or '(미설정 → my_past 안 뜸)'}  auth={auth_note}")
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
            data = _query(base_url, line, pid, k)
        except urllib.error.HTTPError as exc:
            print(f"[HTTP {exc.code}] {exc.read().decode('utf-8', 'ignore')}", file=sys.stderr)
            continue
        except urllib.error.URLError as exc:
            print(f"[연결 실패] {exc.reason} — ai-server({base_url}) 떠 있나요?", file=sys.stderr)
            continue
        print("---")
        print(render(data))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
