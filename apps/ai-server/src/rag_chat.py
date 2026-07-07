#!/usr/bin/env python3
"""RAG grounding 대화형 테스트 클라이언트 — 발화를 ai-server로 보내 grounding을 본다.

**HTTP 클라이언트**다. ai-server의 POST /ai/rag/grounding 을 때린다. DB·키·의존성이
전혀 필요 없어 표준 라이브러리(urllib)만 쓰므로, venv 없이 노트북 어디서든 파일 하나만
복사해 `python rag_chat.py` 로 **그냥 바로 실행**된다. (RAG 로직 자체는 ai-server에서 돈다.)

기본값을 파일에 박아둠 → 외부망에서 아무 설정 없이 실행하면 공인주소(223.194.33.26:24855)로
붙고 VP-004 환자로 my_past(■ 내 과거)까지 바로 조회된다. 필요하면 env/명령으로 덮어쓴다.
(같은 LAN이면 NS_RAG_URL=http://192.168.68.50:8001)

실행: `python rag_chat.py`  (또는 apps/ai-server에서 `python -m src.rag_chat`)
env(선택, 기본값 덮어쓰기용):
  NS_RAG_URL     ai-server 베이스 URL (기본 아래 DEFAULT_URL)
  NS_PATIENT_ID  VP 환자 UUID       (기본 아래 DEFAULT_PATIENT_ID)
  NS_K           슬롯별 top-k 1~10   (기본 3)

명령: 발화 입력 / ":p <uuid|VP-00N>" patient 변경 / ":k 5" k 변경 / ":q"/exit 종료.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

# ── 기본값(그냥 실행 대상) — env로 덮어쓸 수 있음. ────────────────────────────
# ai-server 공인 주소(공유기: 외부 24855 → 내부 DGX:35003 → 컨테이너 8001).
# 외부망 어디서든 이 주소로 바로 붙는다. 같은 LAN이면 NS_RAG_URL=http://192.168.68.50:8001 로 덮어쓰면 됨.
DEFAULT_URL = "http://223.194.33.26:24855"

# load_simulations로 적재된 VP 페르소나(결정론적 uuid5, 비밀 아님). :p VP-004 로도 전환 가능.
PERSONAS = {
    "VP-001": "adc981a1-07e6-5325-8cf0-e352ec2b45e5",  # ANXIETY
    "VP-002": "38066e4e-b2b5-5e06-bf38-4fbff4db3b76",  # DEPRESSION 경증
    "VP-003": "e75f5b7f-a126-50eb-8e9a-9a8860add584",  # DEPRESSION 중증
    "VP-004": "83ba5822-5088-5955-94a0-24ec569dc840",  # DEPRESSION 중증 악화
}
DEFAULT_PATIENT_ID = PERSONAS["VP-004"]


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
    """POST /ai/rag/grounding — 실패 시 예외를 올려 REPL이 잡게 한다."""
    body = json.dumps(
        {"utterance": utterance, "patient_id": patient_id, "k": k}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/ai/rag/grounding",
        data=body,
        headers={"Content-Type": "application/json"},
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
    # env가 있으면 우선, 없으면 파일에 박아둔 기본 환자(VP-004)로 그냥 동작.
    pid = _parse_uuid(os.environ.get("NS_PATIENT_ID", "")) or DEFAULT_PATIENT_ID
    print(f"RAG 테스트 클라이언트  server={base_url}  k={k}  "
          f"patient_id={pid or '(미설정 → my_past 안 뜸)'}")
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
