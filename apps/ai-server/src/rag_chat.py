#!/usr/bin/env python3
"""RAG grounding 대화형 조회기 — 발화를 입력하면 grounding 결과를 출력한다.

이미 배포된 api의 두 엔드포인트만 HTTP로 호출한다(읽기 전용):
  1) POST /api/v1/auth/login       → clinician JWT 획득
  2) POST /api/v1/rag/grounding    → 발화당 grounding(유사사례/지식/증상/후속질문)

표준 라이브러리만 사용 → 노트북에서 `python3 apps/ai-server/src/rag_chat.py` 만으로 실행(설치 불필요).

접속 대상/계정은 환경변수로 바꾼다(기본값 = 외부망 공인IP + 데모 clinician):
  NS_BASE_URL   기본 http://223.194.33.26:28845   (같은 WiFi면 http://192.168.68.50:35002)
  NS_EMAIL      기본 clinician@neurosync.demo
  NS_PASSWORD   기본 Demo!Password-2026            (데모 비밀번호, 실제 비밀 아님)
  NS_ROLE       기본 clinician
  NS_K          기본 3                             (슬롯별 top-k, 1~10)

명령: 발화를 그냥 입력 / ":k 5" k 변경 / ":q" 또는 "exit" 종료.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("NS_BASE_URL", "http://223.194.33.26:28845").rstrip("/")
EMAIL = os.environ.get("NS_EMAIL", "clinician@neurosync.demo")
PASSWORD = os.environ.get("NS_PASSWORD", "Demo!Password-2026")
ROLE = os.environ.get("NS_ROLE", "clinician")


def _post(path: str, payload: dict, token: str | None = None) -> dict:
    """JSON POST. (status_code, parsed_body) 대신 성공 body만 반환, 실패는 예외."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {exc.code} {path}\n{body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"연결 실패 {BASE_URL}{path} — {exc.reason}\n"
                           f"같은 WiFi면 NS_BASE_URL을 192.168.68.50:35002, "
                           f"외부망이면 <공인IP>:28845 로 확인하세요.") from exc


def login() -> str:
    body = _post("/api/v1/auth/login",
                 {"email": EMAIL, "password": PASSWORD, "role": ROLE})
    return body["data"]["accessToken"]


def render(grounding: dict) -> str:
    lines: list[str] = []
    cases = grounding.get("similar_cases") or []
    lines.append(f"■ 유사사례(남의 사례) {len(cases)}건")
    for c in cases:
        lines.append(f"   [{c.get('score')}] {c.get('disease_class')} — {c.get('situation')}")

    past = grounding.get("my_past") or []
    if past:
        lines.append(f"■ 내 과거 {len(past)}건")
        for p in past:
            lines.append(f"   [{p.get('score')}] {p.get('disease_class')} — {p.get('situation')}")

    know = grounding.get("knowledge") or []
    lines.append(f"■ 지식(QA) {len(know)}건")
    for q in know:
        lines.append(f"   [{q.get('score')}] Q: {q.get('question')}")
        lines.append(f"            A: {q.get('answer')}")

    lines.append(f"■ 감지된 증상: {grounding.get('mentioned_symptoms') or []}")

    fu = grounding.get("follow_up")
    if fu:
        lines.append(f"■ 후보질병: {fu.get('candidate_disease')}")
        lines.append(f"   미확인 증상(후속질문): {fu.get('follow_up_symptoms') or []}")
    else:
        lines.append("■ 후보질병: (없음)")
    return "\n".join(lines)


def main() -> int:
    k = int(os.environ.get("NS_K", "3"))
    print(f"접속: {BASE_URL}  계정: {EMAIL} ({ROLE})  k={k}")
    try:
        token = login()
    except RuntimeError as exc:
        print(f"[로그인 실패] {exc}", file=sys.stderr)
        return 1
    print("로그인 OK. 발화를 입력하세요. (:k N = k변경, :q/exit = 종료)\n")

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
        if line.startswith(":k"):
            try:
                k = max(1, min(10, int(line.split()[1])))
                print(f"(k={k})")
            except (IndexError, ValueError):
                print("사용법: :k 5")
            continue

        try:
            body = _post("/api/v1/rag/grounding", {"utterance": line, "k": k}, token)
        except RuntimeError as exc:
            # 토큰 만료(401)면 한 번 재로그인 후 재시도.
            if "HTTP 401" in str(exc):
                try:
                    token = login()
                    body = _post("/api/v1/rag/grounding", {"utterance": line, "k": k}, token)
                except RuntimeError as exc2:
                    print(f"[오류] {exc2}", file=sys.stderr)
                    continue
            else:
                print(f"[오류] {exc}", file=sys.stderr)
                continue

        print("---")
        print(render(body.get("data", {})))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
