"""시뮬레이션 대화(docs/ai/simulation_results) → DB 적재 (오프라인, sync).

VP-001~004 각 페르소나를 "실제 환자가 입력한 것처럼" 5개 테이블에 채운다:
  users → patient_profiles → sessions → messages → rag.session_insights

데이터 소스 (더미 0개):
  - 인구정보(이름/나이/성별/거주지): docs/ai/personas/VP-00X_*.md 표
  - 대화 원문: *_conversation.json  turns[]
  - 임상 슬롯:  *_conversation.json  final_slots[]  → session_insights.slots(JSONB)
  - class/자살플래그: 페르소나별 규칙 매핑(아래 PERSONA_META)

ID는 uuid5로 결정론적 생성 → 재실행해도 중복 없음(ON CONFLICT).
임베딩은 corpus와 동일 Solar 모델(embed_passages) → my_past 벡터검색 유효.
message/name은 api와 동일 AES-GCM(crypto.encrypt_str) → 앱이 복호화 가능.

실행: `python -m src.rag.tooling.load_simulations`
필요 env: DATABASE_URL, ENCRYPTION_KEY(api와 동일), UPSTAGE_API_KEY, EMBED_BASE_URL
"""

from __future__ import annotations

import glob
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from src.rag import crypto
from src.rag.embed import PASSAGE_MODEL, USE_DUMMY, embed_passages, to_pgvector
from src.rag.tooling._db import connect

MODEL_TAG = "dummy" if USE_DUMMY else PASSAGE_MODEL  # embed_corpus와 동일 태그

# 프로젝트 루트 (…/neurosync). 이 파일: apps/ai-server/src/rag/tooling/load_simulations.py
ROOT = Path(__file__).resolve().parents[5]
SIM_DIR = ROOT / "docs" / "ai" / "simulation_results"
PERSONA_DIR = ROOT / "docs" / "ai" / "personas"

# uuid5 네임스페이스 (프로젝트 고정) — 결정론적 ID
NS = uuid.uuid5(uuid.NAMESPACE_DNS, "neurosync.sim")

SIM_PASSWORD = "Demo!Sim-2026"  # 데모용, 실제 비밀 아님. 로그인 계정 식별자.

# 페르소나별 class(rag 3분류) + 자살플래그. 근거는 각 persona.md 위험평가/척도.
PERSONA_META = {
    "VP-001": {"class": "ANXIETY", "suicidal": False},     # PHQ7/GAD8, 자살사고 없음
    "VP-002": {"class": "DEPRESSION", "suicidal": False},   # 재진 경증, 호전 중
    "VP-003": {"class": "DEPRESSION", "suicidal": True},    # 중증, 수동적 자살사고 매일
    "VP-004": {"class": "DEPRESSION", "suicidal": True},    # 중증 악화, 수동적 자살사고
}

CURRENT_YEAR = 2026
MINOR_AGE_CUTOFF = 14  # api patient_profiles.is_minor 판정 기준(만 14세 미만)


def _persona_demographics(persona_id: str) -> dict:
    """persona.md Demographics 표에서 이름/나이/성별/거주지 추출."""
    hits = sorted(PERSONA_DIR.glob(f"{persona_id}_*.md"))
    if not hits:
        raise FileNotFoundError(f"persona md 없음: {persona_id}")
    text = hits[0].read_text(encoding="utf-8")

    def row(label: str) -> str | None:
        m = re.search(rf"\|\s*{label}\s*\|\s*([^|]+?)\s*\|", text)
        return m.group(1).strip() if m else None

    name = (row("이름") or "").split("(")[0].strip()  # "김서연 (가명)" → "김서연"
    age_raw = row("나이") or ""
    age_m = re.search(r"(\d+)", age_raw)
    age = int(age_m.group(1)) if age_m else 30
    return {
        "name": name,
        "birth_year": CURRENT_YEAR - age,
        "gender": row("성별"),
        "region": row("거주지"),
    }


def _phq_gad(persona_id: str) -> tuple[int | None, int | None]:
    """persona.md에서 PHQ-9/GAD-7 예상 점수(첫 '~N') 추출. 실패 시 None."""
    hits = sorted(PERSONA_DIR.glob(f"{persona_id}_*.md"))
    text = hits[0].read_text(encoding="utf-8") if hits else ""

    def score(scale: str) -> int | None:
        m = re.search(rf"{scale}\s*\|\s*~?(\d+)", text)
        return int(m.group(1)) if m else None

    return score("PHQ-9"), score("GAD-7")


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _situation(final_slots: list[dict]) -> str:
    """final_slots에서 검색용 요약문 구성 (임베딩 + 저장 대상)."""
    slots = {s["key"]: s["value"] for s in final_slots}
    parts = [
        slots.get("chief_complaint", ""),
        slots.get("history_of_present_illness", ""),
        slots.get("risk_assessment", ""),
    ]
    return " / ".join(p for p in parts if p)


def _load_one(cur, conv_path: Path) -> dict:
    doc = json.loads(conv_path.read_text(encoding="utf-8"))
    persona_id = doc["persona_id"]           # "VP-001"
    conv_session = doc["session_id"]         # "f1_VP-001" (UUID 아님)
    meta = PERSONA_META.get(persona_id, {"class": None, "suicidal": False})
    demo = _persona_demographics(persona_id)
    phq9, gad7 = _phq_gad(persona_id)

    user_id = uuid.uuid5(NS, f"user:{persona_id}")
    session_id = uuid.uuid5(NS, f"session:{conv_session}")

    # 1) users (암호화 불필요)
    cur.execute(
        """INSERT INTO users (id, email, password_hash, role)
           VALUES (%s, %s, %s, 'patient') ON CONFLICT (id) DO NOTHING""",
        (user_id, f"{persona_id.lower()}@sim.local", crypto.hash_password(SIM_PASSWORD)),
    )

    # 2) patient_profiles (name 암호화). is_minor는 실제 DB에서 일반 NOT NULL 컬럼이라
    #    api 판정식(만 14세 미만)과 동일하게 여기서 계산해 삽입.
    is_minor = (CURRENT_YEAR - demo["birth_year"]) < MINOR_AGE_CUTOFF
    cur.execute(
        """INSERT INTO patient_profiles
             (user_id, name_encrypted, birth_year, is_minor, gender, region)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (user_id) DO UPDATE
             SET name_encrypted = EXCLUDED.name_encrypted, birth_year = EXCLUDED.birth_year,
                 is_minor = EXCLUDED.is_minor""",
        (
            user_id,
            crypto.encrypt_str(demo["name"], aad=crypto.profile_aad(str(user_id), "name")),
            demo["birth_year"],
            is_minor,
            demo["gender"],
            demo["region"],
        ),
    )

    # 3) sessions (암호화 불필요)
    cur.execute(
        """INSERT INTO sessions (id, patient_id, status, created_at, submitted_at)
           VALUES (%s, %s, 'submitted', %s, %s)
           ON CONFLICT (id) DO NOTHING""",
        (session_id, user_id, _parse_ts(doc.get("started_at")), _parse_ts(doc.get("ended_at"))),
    )

    # 4) messages (content 암호화). turn마다 환자발화(user) + AI응답(ai).
    n_msg = 0
    for turn in doc.get("turns", []):
        ts = _parse_ts(turn.get("timestamp"))
        for role, key in (("user", "patient_message"), ("ai", "agent_response")):
            content = turn.get(key)
            if not content:
                continue
            mid = uuid.uuid5(NS, f"msg:{conv_session}:{turn.get('turn')}:{role}")
            cur.execute(
                """INSERT INTO messages (id, session_id, role, content_encrypted, created_at)
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                (
                    mid,
                    session_id,
                    role,
                    crypto.encrypt_str(content, aad=crypto.message_aad(str(session_id), str(mid))),
                    ts,
                ),
            )
            n_msg += 1

    # 5) rag.session_insights — my_past 검색 대상. situation은 평문바이트(_dec 호환).
    situation = _situation(doc.get("final_slots", []))
    embedding = embed_passages([situation])[0]
    slots_obj = {s["key"]: s["value"] for s in doc.get("final_slots", [])}
    cur.execute(
        """INSERT INTO rag.session_insights
             (session_id, patient_id, class, phq9_score, gad7_score, flag_suicidal,
              situation_encrypted, slots, embedding, embedding_model)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
           ON CONFLICT (session_id) DO UPDATE SET
             class=EXCLUDED.class, slots=EXCLUDED.slots,
             situation_encrypted=EXCLUDED.situation_encrypted,
             embedding=EXCLUDED.embedding, embedding_model=EXCLUDED.embedding_model""",
        (
            session_id,
            user_id,
            meta["class"],
            phq9,
            gad7,
            meta["suicidal"],
            situation.encode("utf-8"),  # 평문바이트 (retrieval._dec가 그대로 decode)
            Jsonb(slots_obj),
            to_pgvector(embedding),
            MODEL_TAG,
        ),
    )

    return {
        "persona": persona_id,
        "name": demo["name"],
        "patient_id": str(user_id),
        "session_id": str(session_id),
        "messages": n_msg,
        "slots": len(slots_obj),
        "class": meta["class"],
    }


def main() -> int:
    conv_files = sorted(glob.glob(str(SIM_DIR / "VP-*" / "*_conversation.json")))
    if not conv_files:
        print(f"[오류] conversation.json 없음: {SIM_DIR}")
        return 1
    print(f"적재 대상 {len(conv_files)}건 (임베딩 모델={MODEL_TAG})\n", flush=True)

    conn = connect()
    results = []
    try:
        with conn.cursor() as cur:
            for f in conv_files:
                r = _load_one(cur, Path(f))
                results.append(r)
                print(
                    f"  ✓ {r['persona']} {r['name']}  patient_id={r['patient_id']}  "
                    f"msg={r['messages']} slots={r['slots']} class={r['class']}",
                    flush=True,
                )
        conn.commit()
    finally:
        conn.close()

    print("\n=== rag_chat.py 검증용 patient_id ===", flush=True)
    for r in results:
        print(f"  {r['persona']} {r['name']}: {r['patient_id']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
