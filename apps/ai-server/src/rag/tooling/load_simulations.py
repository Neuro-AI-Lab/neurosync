"""시뮬레이션 대화(docs/ai/simulation_results) → DB 적재 (오프라인, sync).

정크(테스트리그/미완성) 배제 후 session_id별 최신 세션만 "실제 환자가
입력한 것처럼" 채운다. 초·재세션이 같은 환자로 묶여 종단 데이터를 형성:
  users → patient_profiles → sessions → messages → rag.session_insights
                → questionnaire_results → rag.longitudinal_series

데이터 소스 (더미 0개):
  - 인구정보(이름/나이/성별/거주지): docs/ai/personas/VP-00X_*.md 표
  - 대화 원문: *_conversation.json  turns[]  (턴0·1 시드 겹침은 dedup)
  - 임상 슬롯:  *_conversation.json  final_slots[]  → session_insights.slots(JSONB)
  - 추정질환/grounding(F2): *_domain_inference.json → session_insights 신설 컬럼
  - 문진 결과(F3): *_survey.json(administered) → questionnaire_results
      + longitudinal_series(척도별 시점)
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
# VP-010/011/012 (PLAN-2026-W28-Q W6, plan §9): 셋 다 크라이시스 전면
# 배제 설계(§8 disclosed limitation) — SI/자해 명확히 negative, suicidal=False.
PERSONA_META = {
    "VP-001": {"class": "ANXIETY", "suicidal": False},     # PHQ7/GAD8, 자살사고 없음
    "VP-002": {"class": "DEPRESSION", "suicidal": False},   # 재진 경증, 호전 중
    "VP-003": {"class": "DEPRESSION", "suicidal": True},    # 중증, 수동적 자살사고 매일
    "VP-004": {"class": "DEPRESSION", "suicidal": True},    # 중증 악화, 수동적 자살사고
    # 축소보고형, 초진. Ground truth 코모비드 우울(PHQ-9~13)+불안(GAD-7~11) —
    # 두 축이 비등하며, 우울이 CC/슬롯 문서(§2/§4)에서 먼저 명명되므로
    # DEPRESSION을 대표 class로 선택(단일 판단, CVR-004 Finding 1이 이미
    # 이 코모비드 특성 자체를 지적 — data의 golden-label 표기와는 별개 결정).
    "VP-010": {"class": "DEPRESSION", "suicidal": False},
    # 신체화-가면우울, 초진. 기저 진단(§2 anchor) = 중등도 주요우울장애 —
    # DEPRESSION 명확.
    "VP-011": {"class": "DEPRESSION", "suicidal": False},
    # 만성 알코올사용장애, 초진. 알코올이 stated presenting concern(§2) —
    # ADDICTION(우울 동반이나 임상적 초점은 알코올, §2 comorbidity note).
    "VP-012": {"class": "ADDICTION", "suicidal": False},
}

CURRENT_YEAR = 2026
MINOR_AGE_CUTOFF = 14  # api patient_profiles.is_minor 판정 기준(만 14세 미만)

# F3 survey_scorer의 ScaleName 5종 (0008 마이그레이션 CHECK 제약과 동일).
ALLOWED_SCALES = {"PHQ-9", "GAD-7", "PHQ-4", "WHO-5", "AUDIT-C"}

# 테스트리그 세션 식별자(정크). 실제 임상 세션(f1_VP-00X[_followup])만 남긴다.
#   sc\d… : 시나리오 주입,  _injected/_rep\d/_phr/_audio : 변형 리그
_TESTRIG = re.compile(r"(^sc\d|_injected|_rep\d|_phr|_audio)")


def _max_patient_run(turns: list[dict]) -> int:
    """연속으로 동일한 patient_message가 반복된 최대 길이(정크 판정용)."""
    prev = None
    run = 0
    mx = 0
    for t in turns:
        pm = (t.get("patient_message") or "").strip()
        if pm and pm == prev:
            run += 1
        else:
            run = 1
            prev = pm
        mx = max(mx, run)
    return mx


def _select_conv_files() -> list[Path]:
    """정크 배제 후 session_id별 최신 conversation 1개를 고른다.

    필터: 실제 세션(테스트리그 아님) AND turns>=10 AND 연속중복<=2(턴0·1 시드
    겹침만 허용). 파일명이 시간순 정렬되므로 마지막(최신)이 세션 대표.
    """
    best: dict[str, Path] = {}
    for f in sorted(glob.glob(str(SIM_DIR / "VP-*" / "*_conversation.json"))):
        try:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sid = doc.get("session_id")
        turns = doc.get("turns", [])
        if not sid or _TESTRIG.search(sid):
            continue
        if len(turns) < 10 or _max_patient_run(turns) > 2:
            continue
        best[sid] = Path(f)  # 정렬상 뒤 = 최신
    return [best[s] for s in sorted(best)]


def _newest_domain_inference(persona_dir: Path, conv_session: str) -> dict | None:
    """session_id가 일치하는 최신 domain_inference.json(F2 산출물) 반환."""
    found = None
    for f in sorted(persona_dir.glob("*_domain_inference.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("session_id") == conv_session:
            found = d  # 정렬상 뒤 = 최신
    return found


def _administered_surveys(persona_dir: Path, conv_session: str) -> list[dict]:
    """해당 세션에서 실제 시행된(administered) 문진 결과들을 시간순으로 반환.

    outcome!=administered(no_questionnaire_indicated 등), 미허용 척도,
    score_result 없음은 제외 → questionnaire_results NOT NULL/CHECK 안전.
    """
    out = []
    for f in sorted(persona_dir.glob("*_survey.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if s.get("session_id") != conv_session:
            continue
        if s.get("outcome") != "administered":
            continue
        if s.get("scale_name") not in ALLOWED_SCALES:
            continue
        if not (s.get("score_result") or {}).get("severity"):
            continue
        out.append(s)
    return out


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
    #    턴0·1 시드 겹침: 두 턴의 patient_message가 동일한 알려진 현상 →
    #    직전과 같은 환자발화는 1회만 적재(agent_response는 서로 달라 그대로).
    n_msg = 0
    prev_pm = None
    for turn in doc.get("turns", []):
        ts = _parse_ts(turn.get("timestamp"))
        pm = turn.get("patient_message")
        pm_dedup = None if (pm and pm == prev_pm) else pm
        if pm:
            prev_pm = pm
        for role, content in (("user", pm_dedup), ("ai", turn.get("agent_response"))):
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
    #    F2 산출물(추정질환/grounding)은 domain_inference.json에서 가져온다.
    #    class(3분류 도메인)는 PERSONA_META 유지, 추정질환은 신설 컬럼에 분리 저장.
    situation = _situation(doc.get("final_slots", []))
    embedding = embed_passages([situation])[0]
    slots_obj = {s["key"]: s["value"] for s in doc.get("final_slots", [])}

    di = _newest_domain_inference(conv_path.parent, conv_session)
    apd = di.get("ai_predicted_disease") if di else None
    ai_predicted = Jsonb(apd) if apd else None
    grounding = (
        Jsonb({"domain_candidates": di.get("domain_candidates")}) if di else None
    )
    rec_q = (apd or {}).get("recommended_questionnaire")  # 없으면 NULL(허위 금지)

    cur.execute(
        """INSERT INTO rag.session_insights
             (session_id, patient_id, class, phq9_score, gad7_score, flag_suicidal,
              situation_encrypted, slots, embedding, embedding_model,
              ai_predicted_disease, grounding, recommended_questionnaire)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s)
           ON CONFLICT (session_id) DO UPDATE SET
             class=EXCLUDED.class, slots=EXCLUDED.slots,
             situation_encrypted=EXCLUDED.situation_encrypted,
             embedding=EXCLUDED.embedding, embedding_model=EXCLUDED.embedding_model,
             ai_predicted_disease=EXCLUDED.ai_predicted_disease,
             grounding=EXCLUDED.grounding,
             recommended_questionnaire=EXCLUDED.recommended_questionnaire""",
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
            ai_predicted,
            grounding,
            rec_q,
        ),
    )

    # 6) questionnaire_results — 실제 시행된 문진(administered)만. (session,type)당
    #    최신 1건(UNIQUE 제약) → 척도별 재시행은 최신 점수로 upsert.
    surveys = _administered_surveys(conv_path.parent, conv_session)
    n_qr = 0
    for s in surveys:  # 시간순 → 뒤(최신)가 이김
        scale = s["scale_name"]
        sr = s["score_result"]
        qid = uuid.uuid5(NS, f"qr:{conv_session}:{scale}")
        cur.execute(
            """INSERT INTO questionnaire_results
                 (id, session_id, type, answers, total_score, severity, completed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (session_id, type) DO UPDATE SET
                 answers=EXCLUDED.answers, total_score=EXCLUDED.total_score,
                 severity=EXCLUDED.severity, completed_at=EXCLUDED.completed_at""",
            (
                qid,
                session_id,
                scale,
                Jsonb(s.get("responses")),
                sr["total_score"],
                sr["severity"],
                _parse_ts(s.get("timestamp")),
            ),
        )
        n_qr += 1

    # 7) rag.longitudinal_series — F4 종단 시계열. 문진 시행 파일마다 1 시점.
    #    (patient_id, scale, measured_at) UNIQUE로 멱등. 초·재세션이 같은 환자로
    #    묶여 척도별 다중 시점을 형성한다.
    n_long = 0
    for s in surveys:
        measured_at = _parse_ts(s.get("timestamp"))
        if measured_at is None:
            continue
        sr = s["score_result"]
        cur.execute(
            """INSERT INTO rag.longitudinal_series
                 (patient_id, session_id, scale, total_score, severity,
                  measured_at, series)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (patient_id, scale, measured_at) DO NOTHING""",
            (
                user_id,
                session_id,
                s["scale_name"],
                sr["total_score"],
                sr["severity"],
                measured_at,
                Jsonb(s.get("responses")),
            ),
        )
        n_long += 1

    return {
        "persona": persona_id,
        "name": demo["name"],
        "patient_id": str(user_id),
        "session_id": str(session_id),
        "conv_session": conv_session,
        "messages": n_msg,
        "slots": len(slots_obj),
        "class": meta["class"],
        "disease": next(iter((apd or {}).get("candidates") or []), {}).get("disease"),
        "questionnaires": n_qr,
        "longitudinal": n_long,
    }


def main() -> int:
    conv_files = _select_conv_files()  # 정크 배제 + session_id별 최신 1개
    if not conv_files:
        print(f"[오류] 적재할 클린 세션 없음: {SIM_DIR}")
        return 1
    print(f"적재 대상 {len(conv_files)}세션 (정크 배제 후, 임베딩 모델={MODEL_TAG})\n", flush=True)

    conn = connect()
    results = []
    try:
        with conn.cursor() as cur:
            for f in conv_files:
                r = _load_one(cur, Path(f))
                results.append(r)
                print(
                    f"  ✓ {r['conv_session']:18s} {r['name']}  "
                    f"msg={r['messages']} slots={r['slots']} class={r['class']} "
                    f"qr={r['questionnaires']} long={r['longitudinal']} "
                    f"추정={r['disease']}",
                    flush=True,
                )
        conn.commit()
    finally:
        conn.close()

    print("\n=== rag_chat.py 검증용 patient_id (persona별) ===", flush=True)
    seen = {}
    for r in results:
        seen.setdefault(r["persona"], r["patient_id"])
    for persona, pid in seen.items():
        print(f"  {persona}: {pid}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
