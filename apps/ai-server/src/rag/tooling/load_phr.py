"""PHR 샘플(docs/ai/samples/phr) → rag.phr_records 적재 (오프라인, sync).

페르소나별 medications/visits FHIR 파일을 PatientHistoryAgent로 파싱해
MedicationEvent / HealthcareVisit 필드를 rag.phr_records 컬럼에 **정규화** 저장한다.
추출 로직은 agents/patient_history.py 재사용 — 이 로더는 새 파싱을 하지 않는다.

설계(사용자 승인):
  - user_id = uuid5(NS, "user:VP-00X") : load_simulations와 동일 → 기존 sim 유저의
    PHR로 연결(FK 무결). 해당 user 미존재 시 경고 후 스킵(먼저 load_simulations 필요).
  - id = uuid5(NS_PHR, "{record_type}:{persona}:{seq}") : 결정론적 → 재적재 멱등
    (ON CONFLICT (id) DO UPDATE).
  - 환자명: 시뮬 샘플은 fake 페르소나명이라 Patient.name.text 원문을 patient_name에
    저장(파서 기본 해시 대신). 실데이터 전환 시 암호화는 후속 phase.
  - 약효분류(psychotropic_class 등)는 PatientHistoryAgent.summarize()의 로컬 HIRA
    캐시 패스가 채운다(오프라인, API 미사용).

실행: python -m src.rag.tooling.load_phr
필요 env: DATABASE_URL (임베딩/암호화 불필요)
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from src.adapters.myhealthway_reader import MyHealthWayReader
from src.agents.patient_history import PatientHistoryAgent
from src.rag.tooling._db import connect
from src.rag.tooling.load_simulations import NS  # user_id 네임스페이스 공유(FK 일치)
from src.schemas.phr import PhrSummary

# 프로젝트 루트 (…/neurosync). 이 파일: apps/ai-server/src/rag/tooling/load_phr.py
ROOT = Path(__file__).resolve().parents[5]
PHR_DIR = ROOT / "docs" / "ai" / "samples" / "phr"

# phr_records.id 결정론적 생성용 네임스페이스 (user NS와 분리)
NS_PHR = uuid.uuid5(NS, "phr_records")

PERSONAS = ["VP-001", "VP-002", "VP-003", "VP-004"]


def _persona_files(persona: str) -> list[str]:
    """존재하는 medications/visits 파일 경로만 반환."""
    candidates = [
        PHR_DIR / f"{persona}_medications.json",
        PHR_DIR / f"{persona}_visits.json",
    ]
    return [str(p) for p in candidates if p.is_file()]


def _patient_name(reader: MyHealthWayReader, bundles: list[dict[str, Any]]) -> str:
    """번들의 Patient 리소스에서 원문 성명(name.text)을 직접 추출.

    parse_patient는 PII 보호로 해시만 주므로, sim fake명 원문은 여기서 뽑는다.
    """
    for b in bundles:
        for res in reader.iter_resources(b, "Patient"):
            for n in res.get("name") or []:
                if isinstance(n, dict) and n.get("text"):
                    return str(n["text"])
    return ""


async def _parse(paths: list[str]) -> tuple[PhrSummary, str]:
    """PatientHistoryAgent로 파싱 → (PhrSummary, 원문 환자명)."""
    reader = MyHealthWayReader()
    agent = PatientHistoryAgent(reader=reader)  # efficacy_adapter=None → 로컬 캐시만
    bundles = await agent.load_bundles(paths)
    summary = await agent.summarize(bundles)
    return summary, _patient_name(reader, bundles)


# 재적재 시 파일 수정 반영을 위해 전체 컬럼 갱신.
_MED_UPDATE = """
    source_file=EXCLUDED.source_file, mhid=EXCLUDED.mhid,
    patient_name=EXCLUDED.patient_name, rn_masked=EXCLUDED.rn_masked,
    event_date=EXCLUDED.event_date, facility_name=EXCLUDED.facility_name,
    facility_address=EXCLUDED.facility_address, kd_code=EXCLUDED.kd_code,
    hira_ingredient_code=EXCLUDED.hira_ingredient_code,
    product_name=EXCLUDED.product_name, ingredient_name=EXCLUDED.ingredient_name,
    days_supply=EXCLUDED.days_supply, daily_frequency=EXCLUDED.daily_frequency,
    dose_per_take=EXCLUDED.dose_per_take, dose_form_text=EXCLUDED.dose_form_text,
    efficacy_class_no=EXCLUDED.efficacy_class_no,
    efficacy_class_name=EXCLUDED.efficacy_class_name,
    psychotropic_class=EXCLUDED.psychotropic_class
"""

_VISIT_UPDATE = """
    source_file=EXCLUDED.source_file, mhid=EXCLUDED.mhid,
    patient_name=EXCLUDED.patient_name, rn_masked=EXCLUDED.rn_masked,
    event_date=EXCLUDED.event_date, facility_name=EXCLUDED.facility_name,
    facility_address=EXCLUDED.facility_address, facility_kind=EXCLUDED.facility_kind,
    claim_type=EXCLUDED.claim_type, total_cost=EXCLUDED.total_cost,
    diagnosis_codes=EXCLUDED.diagnosis_codes
"""


def _load_one(cur, persona: str) -> dict[str, Any]:
    paths = _persona_files(persona)
    if not paths:
        return {"persona": persona, "skipped": "파일 없음"}

    summary, name = asyncio.run(_parse(paths))
    user_id = uuid.uuid5(NS, f"user:{persona}")

    # FK 무결: sim 유저가 있어야 PHR을 연결(먼저 load_simulations 필요).
    cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
    if cur.fetchone() is None:
        return {"persona": persona, "skipped": f"user 없음({user_id}) — load_simulations 먼저"}

    mhid = summary.patient.mhid or None
    rn_masked = summary.patient.rn_masked or None
    med_file = f"{persona}_medications.json"
    visit_file = f"{persona}_visits.json"

    n_med = 0
    for i, m in enumerate(summary.medications):
        rid = uuid.uuid5(NS_PHR, f"medication:{persona}:{i}")
        cur.execute(
            f"""INSERT INTO rag.phr_records
                 (id, patient_id, persona_id, record_type, source_file,
                  mhid, patient_name, rn_masked,
                  event_date, facility_name, facility_address,
                  kd_code, hira_ingredient_code, product_name, ingredient_name,
                  days_supply, daily_frequency, dose_per_take, dose_form_text,
                  efficacy_class_no, efficacy_class_name, psychotropic_class)
               VALUES (%s,%s,%s,'medication',%s, %s,%s,%s, %s,%s,%s,
                       %s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET {_MED_UPDATE}""",
            (
                rid, user_id, persona, med_file,
                mhid, name or None, rn_masked,
                m.dispensed_at, m.pharmacy or None, m.pharmacy_address,
                m.kd_code or None, m.hira_ingredient_code,
                m.product_name or None, m.ingredient_name,
                m.days_supply, m.daily_frequency, m.dose_per_take,
                m.dose_form_text or None,
                m.efficacy_class_no, m.efficacy_class_name or None,
                m.psychotropic_class,
            ),
        )
        n_med += 1

    n_vis = 0
    for i, v in enumerate(summary.visits):
        rid = uuid.uuid5(NS_PHR, f"visit:{persona}:{i}")
        cur.execute(
            f"""INSERT INTO rag.phr_records
                 (id, patient_id, persona_id, record_type, source_file,
                  mhid, patient_name, rn_masked,
                  event_date, facility_name, facility_address,
                  facility_kind, claim_type, total_cost, diagnosis_codes)
               VALUES (%s,%s,%s,'visit',%s, %s,%s,%s, %s,%s,%s, %s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET {_VISIT_UPDATE}""",
            (
                rid, user_id, persona, visit_file,
                mhid, name or None, rn_masked,
                v.visited_at, v.facility_name or None, v.facility_address,
                v.facility_kind, v.claim_type, v.total_cost,
                Jsonb(v.diagnosis_codes),
            ),
        )
        n_vis += 1

    return {
        "persona": persona,
        "name": name,
        "patient_id": str(user_id),
        "medications": n_med,
        "visits": n_vis,
        "psychotropic": len(summary.psychotropic_medications),
    }


def main() -> int:
    conn = connect()
    results = []
    try:
        with conn.cursor() as cur:
            for persona in PERSONAS:
                r = _load_one(cur, persona)
                results.append(r)
                if r.get("skipped"):
                    print(f"  ⚠ {persona}: {r['skipped']}", flush=True)
                else:
                    print(
                        f"  ✓ {persona}  {r['name']}  "
                        f"med={r['medications']} (psych={r['psychotropic']}) "
                        f"visit={r['visits']}",
                        flush=True,
                    )
        conn.commit()
    finally:
        conn.close()

    total_med = sum(r.get("medications", 0) for r in results)
    total_vis = sum(r.get("visits", 0) for r in results)
    print(f"\n적재 완료: medications {total_med} + visits {total_vis} "
          f"= {total_med + total_vis} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
