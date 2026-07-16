"""PatientHistoryAgent — myhealthway PHR raw JSON → PhrSummary.

Layer 2 (도메인 매핑) 담당:
- `MyHealthWayReader.iter_resources` 로 얻은 raw dict → `MedicationEvent` /
  `HealthcareVisit` / `PatientMeta` Pydantic 검증 통과 객체
- 여러 파일 (투약 + 진료) 병합
- 정신과 약물 판정 (성분명 카탈로그)
- Handoff/system prompt용 요약 문자열 생성

설계 문서: _archive/plans/phr_integration_plan.md
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.adapters.hira_drug_efficacy import EfficacyInfo, HiraDrugEfficacyAdapter
from src.adapters.myhealthway_reader import (
    MyHealthWayReader,
    MyHealthWayReadError,
)
from src.agents.base import BaseAgent
from src.data import hira_efficacy_cache
from src.data.psychotropic_classification import classify_efficacy, label
from src.schemas.phr import (
    ClaimType,
    FacilityKind,
    HealthcareVisit,
    MedicationEvent,
    PatientMeta,
    PhrLoadInput,
    PhrSummary,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────


def _safe_date(value: Any) -> date | None:
    """관대한 날짜 파서. 실 PHR 관찰상 대부분 ISO 'YYYY-MM-DD'."""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    # 1순위: ISO 형식 (`2026-04-12` 또는 `2026-04-12T09:00:00`).
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass
    # 2순위: 대시 없는 `YYYYMMDD`.
    if len(s) == 8 and s.isdigit():
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            pass
    return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None


def _first_coding(node: dict[str, Any] | None, system_hint: str | None = None) -> dict[str, Any]:
    """`code.coding[]` 중 system 힌트 일치를 우선 반환.

    - system_hint 지정 & 매칭 있으면 그 coding 반환.
    - system_hint 지정 & 매칭 **없으면 빈 dict 반환** (silent contamination 방지).
      호출자가 다른 system code를 원치 않는 필드(kd_code, hira_code 등)에
      실수로 저장하는 것을 막는다.
    - system_hint 미지정이면 첫 번째 coding 반환.
    """
    if not isinstance(node, dict):
        return {}
    codings = node.get("coding") or []
    if not codings:
        return {}
    if system_hint:
        for c in codings:
            if isinstance(c, dict) and system_hint in str(c.get("system", "")):
                return c
        # system_hint 매칭 실패 → 빈 dict (Bug fix: 다른 system code 오염 방지)
        return {}
    return codings[0] if isinstance(codings[0], dict) else {}


def _pick_organization(
    contained: list[dict[str, Any]] | None,
    exclude_types: set[str] | None = None,
) -> dict[str, Any] | None:
    """`contained[]` 안 Organization 중 우선순위로 하나 선택.

    exclude_types: `type.text` 이 이 집합에 있으면 건너뜀 (예: 보험사).
    """
    if not contained:
        return None
    exclude = exclude_types or set()
    for c in contained:
        if not isinstance(c, dict):
            continue
        if c.get("resourceType") != "Organization":
            continue
        type_text = ((c.get("type") or [{}])[0] or {}).get("text", "")
        if type_text in exclude:
            continue
        return c
    return None


def _facility_kind_from_text(text: str | None) -> FacilityKind:
    if not text:
        return "other"
    t = text.strip()
    if t in ("약국",):
        return "pharmacy"
    if t in ("병의원", "병원", "의원", "상급종합병원", "종합병원", "요양기관"):
        return "medical"
    if t in ("보험사",):
        return "insurer"
    return "other"


def _address_text(org: dict[str, Any] | None) -> str | None:
    if not org:
        return None
    addr_list = org.get("address") or []
    if addr_list and isinstance(addr_list[0], dict):
        return addr_list[0].get("text")
    return None


# ── Parsers (Layer 1 → Layer 2) ──────────────────────────────────────


def parse_patient(resource: dict[str, Any]) -> PatientMeta:
    """Patient 리소스 → PatientMeta."""
    mhid = ""
    rn_masked = ""
    for ident in resource.get("identifier") or []:
        code = _first_coding(ident.get("type")).get("code", "")
        if code == "MHID":
            mhid = str(ident.get("value", ""))
        elif code == "NNKOR":
            rn_masked = str(ident.get("value", ""))
    name = ""
    for n in resource.get("name") or []:
        if isinstance(n, dict) and n.get("text"):
            name = str(n["text"])
            break
    return PatientMeta(
        mhid=mhid,
        name_hash=MyHealthWayReader.compute_name_hash(name),
        rn_masked=rn_masked,
    )


def parse_medication_dispense(resource: dict[str, Any]) -> MedicationEvent:
    """MedicationDispense (+ inline Medication) → MedicationEvent."""
    # 약국
    org = _pick_organization(resource.get("contained"), exclude_types={"보험사"})
    pharmacy = str((org or {}).get("name") or "")
    pharm_addr = _address_text(org)

    # Medication (인라인)
    med_res = ((resource.get("medicationReference") or {}).get("resource")) or {}
    code = med_res.get("code") or {}
    kd = _first_coding(code, system_hint="kdcode")
    product_name = str(code.get("text") or kd.get("display") or "")
    kd_code = str(kd.get("code") or "")

    # 성분 (Substance)
    ingredient_name: str | None = None
    hira_code: str | None = None
    for ing in med_res.get("ingredient") or []:
        sub_res = ((ing.get("itemReference") or {}).get("resource")) or {}
        sub_coding = _first_coding(sub_res.get("code"), system_hint="hira.or.kr")
        if sub_coding:
            hira_code = sub_coding.get("code")
            ingredient_name = sub_coding.get("display")
            break

    # 복용 정보
    dose_instr = (resource.get("dosageInstruction") or [{}])[0]
    if not isinstance(dose_instr, dict):
        dose_instr = {}
    timing_repeat = ((dose_instr.get("timing") or {}).get("repeat")) or {}
    dose_and_rate = (dose_instr.get("doseAndRate") or [{}])[0]
    if not isinstance(dose_and_rate, dict):
        dose_and_rate = {}
    dose_quantity = dose_and_rate.get("doseQuantity") or {}

    days_supply = _safe_int((resource.get("daysSupply") or {}).get("value"))
    daily_freq = _safe_int(timing_repeat.get("frequency"))
    dose_per_take = _safe_float(dose_quantity.get("value"))
    dose_form_text = str(dose_instr.get("text") or "")

    when = resource.get("whenPrepared") or resource.get("whenHandedOver")
    dispensed_at = _safe_date(when)

    return MedicationEvent(
        dispensed_at=dispensed_at,
        pharmacy=pharmacy,
        pharmacy_address=pharm_addr,
        kd_code=kd_code,
        hira_ingredient_code=hira_code,
        product_name=product_name,
        ingredient_name=ingredient_name,
        days_supply=days_supply,
        daily_frequency=daily_freq,
        dose_per_take=dose_per_take,
        dose_form_text=dose_form_text,
        # 약효분류는 파싱 단계에서 결정하지 않는다. summarize()의 비동기
        # 분류 패스(_classify_medications)가 캐시/HIRA API로 채운다.
    )


def parse_visit(resource: dict[str, Any]) -> HealthcareVisit:
    """ExplanationOfBenefit → HealthcareVisit."""
    org = _pick_organization(resource.get("contained"), exclude_types={"보험사"})
    facility_name = str((org or {}).get("name") or "")
    facility_addr = _address_text(org)
    org_type_text = ((org or {}).get("type") or [{}])[0].get("text") if org else None
    facility_kind = _facility_kind_from_text(org_type_text)

    claim_type_raw = _first_coding(resource.get("type")).get("code") or "other"
    claim_type: ClaimType = claim_type_raw if claim_type_raw in {
        "pharmacy", "professional", "institutional", "oral", "vision"
    } else "other"

    visited_at = _safe_date((resource.get("billablePeriod") or {}).get("start"))
    # `total`은 프로파일에 따라 dict 또는 list 형태. 첫 유효 value만 추출.
    total_raw = resource.get("total")
    total_value: Any = None
    if isinstance(total_raw, dict):
        total_value = total_raw.get("value")
    elif isinstance(total_raw, list):
        for t in total_raw:
            if isinstance(t, dict) and t.get("value") is not None:
                total_value = t.get("value")
                break
    total_cost = _safe_decimal(total_value)

    diagnosis_codes: list[str] = []
    for diag in resource.get("diagnosis") or []:
        codeable = (diag or {}).get("diagnosisCodeableConcept") or {}
        for c in codeable.get("coding") or []:
            code = (c or {}).get("code")
            if code:
                diagnosis_codes.append(str(code))

    return HealthcareVisit(
        visited_at=visited_at,
        facility_name=facility_name,
        facility_kind=facility_kind,
        facility_address=facility_addr,
        claim_type=claim_type,
        total_cost=total_cost,
        diagnosis_codes=diagnosis_codes,
    )


# ── Agent ─────────────────────────────────────────────────────────────


class PatientHistoryAgent(BaseAgent):
    """PHR 원본 bundle(들) → PhrSummary + F1 소비 요약 텍스트."""

    def __init__(
        self,
        reader: MyHealthWayReader | None = None,
        efficacy_adapter: HiraDrugEfficacyAdapter | None = None,
    ) -> None:
        self._reader = reader or MyHealthWayReader()
        # None이면 로컬 캐시만 사용 (오프라인/테스트). 주입 시 캐시 miss를
        # HIRA 의약품성분약효정보조회서비스로 보충.
        self._efficacy_adapter = efficacy_adapter

    @property
    def agent_name(self) -> str:
        return "patient_history"

    async def run(self, inp: PhrLoadInput, **kwargs: Any) -> PhrSummary:
        """BaseAgent 계약. `PhrLoadInput.bundle_paths` 파일들을 병합 요약."""
        started = time.perf_counter()
        bundles = await self.load_bundles(inp.bundle_paths)
        summary = await self.summarize(bundles)
        summary.latency_ms = (time.perf_counter() - started) * 1000.0
        summary.reason_summary = (
            f"parsed {len(bundles)} bundle(s), "
            f"{summary.total_medication_events} meds "
            f"({len(summary.psychotropic_medications)} psychotropic), "
            f"{summary.total_visits} visits"
        )
        return summary

    async def load_bundles(self, paths: list[str | Path]) -> list[dict[str, Any]]:
        """여러 PHR 파일 순차 로드. 파일별 에러는 개별 로깅 후 스킵."""
        bundles: list[dict[str, Any]] = []
        for p in paths:
            try:
                bundles.append(await self._reader.load_bundle(p))
            except MyHealthWayReadError as exc:
                logger.warning("PHR bundle skipped %s: %s", p, exc)
        return bundles

    async def summarize(self, bundles: list[dict[str, Any]]) -> PhrSummary:
        """여러 bundle 병합 요약 → PhrSummary."""
        patient: PatientMeta | None = None
        med_events: dict[str, MedicationEvent] = {}
        visits: dict[str, HealthcareVisit] = {}

        for bundle in bundles:
            for resource in self._reader.iter_resources(bundle):
                rtype = resource.get("resourceType")
                if rtype == "Patient":
                    parsed = parse_patient(resource)
                    if patient is None:
                        patient = parsed
                    elif parsed.mhid and patient.mhid and parsed.mhid != patient.mhid:
                        # 여러 파일이 다른 사람의 데이터를 담고 있음 — 개인정보
                        # 오염 위험. 첫 Patient만 유지하되 경고를 남긴다.
                        logger.warning(
                            "PHR bundle contains different MHID: seen=%s, ignored=%s. "
                            "다른 사람의 데이터가 섞였을 가능성 — 첫 번째 Patient만 사용.",
                            patient.mhid, parsed.mhid,
                        )
                elif rtype == "MedicationDispense":
                    key = self._resource_key(resource)
                    if key not in med_events:
                        med_events[key] = parse_medication_dispense(resource)
                elif rtype == "ExplanationOfBenefit":
                    key = self._resource_key(resource)
                    if key not in visits:
                        visits[key] = parse_visit(resource)

        # patient 미확보 시 최소 스텁 (파일에 Patient 없어도 파싱은 계속)
        if patient is None:
            patient = PatientMeta(mhid="", name_hash="", rn_masked="")

        medications = sorted(
            med_events.values(),
            key=lambda m: (m.dispensed_at or date.min, m.product_name),
        )
        visit_list = sorted(
            visits.values(),
            key=lambda v: (v.visited_at or date.min, v.facility_name),
        )

        # 약효분류 판정 (캐시 → HIRA API). MedicationEvent in-place 갱신.
        await self._classify_medications(medications)

        psycho = [m for m in medications if m.is_psychotropic]
        psych_visits = sum(1 for v in visit_list if "정신" in v.facility_name)

        # 커버 기간
        all_dates: list[date] = []
        all_dates.extend(m.dispensed_at for m in medications if m.dispensed_at)
        all_dates.extend(v.visited_at for v in visit_list if v.visited_at)
        date_range = (min(all_dates), max(all_dates)) if all_dates else None

        return PhrSummary(
            patient=patient,
            medications=medications,
            visits=visit_list,
            psychotropic_medications=psycho,
            has_psychiatric_history=bool(psycho) or psych_visits > 0,
            date_range=date_range,
            total_medication_events=len(medications),
            total_visits=len(visit_list),
            psychiatric_visit_count=psych_visits,
        )

    async def _classify_medications(self, medications: list[MedicationEvent]) -> None:
        """각 조제 이벤트의 약효분류를 채운다 (캐시 우선, miss 시 HIRA API).

        같은 일반명코드는 run 내 1회만 조회. 코드 없음/미조회 시 psychotropic_class
        는 기본값 UNKNOWN 유지 (정신과로 단정하지 않음)."""
        resolved: dict[str, EfficacyInfo | None] = {}
        for m in medications:
            code = (m.hira_ingredient_code or "").strip()
            if not code:
                continue
            if code not in resolved:
                resolved[code] = await self._resolve_efficacy(code)
            info = resolved[code]
            if info is None:
                continue
            m.efficacy_class_no = info.meft_div_no
            m.efficacy_class_name = info.div_nm
            m.psychotropic_class = classify_efficacy(info.meft_div_no)

    async def _resolve_efficacy(self, code: str) -> EfficacyInfo | None:
        """캐시 hit 우선, miss & 어댑터 존재 시 HIRA API 조회."""
        info = hira_efficacy_cache.lookup(code)
        if info is not None:
            return info
        if self._efficacy_adapter is not None:
            return await self._efficacy_adapter.get_efficacy(code)
        return None

    def to_system_prompt_note(self, summary: PhrSummary) -> str:
        """LLM system prompt에 붙일 짧은 자연어 요약."""
        if not summary.has_psychiatric_history:
            base = "환자의 개인건강기록(PHR)에서 정신과 진료·투약 이력은 확인되지 않습니다."
        else:
            classes = sorted(
                {label(m.psychotropic_class) for m in summary.psychotropic_medications}
            )
            recent = (
                summary.psychotropic_medications[-1]
                if summary.psychotropic_medications
                else None
            )
            recent_line = ""
            if recent and recent.dispensed_at:
                recent_line = (
                    f" 최근 조제: {recent.product_name} ({recent.dispensed_at.isoformat()})"
                )
            base = (
                "환자의 PHR에서 정신과 관련 이력이 확인됩니다. "
                f"약물군: {', '.join(classes)}. "
                f"정신과 관련 방문 {summary.psychiatric_visit_count}회."
                f"{recent_line}"
            )
        span = ""
        if summary.date_range:
            span = f" (커버 기간: {summary.date_range[0]} ~ {summary.date_range[1]})"
        return base + span

    def to_handoff_snippet(self, summary: PhrSummary) -> dict[str, Any]:
        """Handoff 문서 삽입용 구조화 데이터."""
        return {
            "phr": {
                "patient_mhid": summary.patient.mhid,
                "has_psychiatric_history": summary.has_psychiatric_history,
                "date_range": (
                    [summary.date_range[0].isoformat(), summary.date_range[1].isoformat()]
                    if summary.date_range
                    else None
                ),
                "psychotropic_medications": [
                    {
                        "dispensed_at": m.dispensed_at.isoformat() if m.dispensed_at else None,
                        "product_name": m.product_name,
                        "ingredient_name": m.ingredient_name,
                        "psychotropic_class": m.psychotropic_class,
                        "efficacy_class_no": m.efficacy_class_no,
                        "efficacy_class_name": m.efficacy_class_name,
                        "days_supply": m.days_supply,
                        "daily_frequency": m.daily_frequency,
                    }
                    for m in summary.psychotropic_medications
                ],
                "psychiatric_visit_count": summary.psychiatric_visit_count,
                "total_medications": summary.total_medication_events,
                "total_visits": summary.total_visits,
            }
        }

    # ── Internal ─────────────────────────────────────────────────────

    @staticmethod
    def _resource_key(resource: dict[str, Any]) -> str:
        """중복 제거용 안정 키. identifier[0].value > id 순."""
        idents = resource.get("identifier") or []
        for i in idents:
            v = (i or {}).get("value")
            if v:
                return str(v)
        return str(resource.get("id") or f"anon-{id(resource)}")


# ── Optional CLI (재현용) ─────────────────────────────────────────────


def _cli() -> int:
    import argparse
    import asyncio

    ap = argparse.ArgumentParser(description="PatientHistoryAgent CLI (dev)")
    ap.add_argument("--file", "-f", action="append", required=True,
                    help="PHR JSON 파일 경로 (여러 번 사용 가능)")
    args = ap.parse_args()

    async def run():
        agent = PatientHistoryAgent()
        bundles = await agent.load_bundles(args.file)
        summary = await agent.summarize(bundles)
        print("=" * 60)
        print(f"MHID: {summary.patient.mhid}")
        print(f"Name hash: {summary.patient.name_hash}")
        print(f"Date range: {summary.date_range}")
        print(f"Medications: {summary.total_medication_events} "
              f"(psychotropic {len(summary.psychotropic_medications)})")
        print(
            f"Visits: {summary.total_visits} "
            f"(psychiatric-name {summary.psychiatric_visit_count})"
        )
        print(f"has_psychiatric_history: {summary.has_psychiatric_history}")
        print()
        print("=== System prompt note ===")
        print(agent.to_system_prompt_note(summary))
        print()
        print("=== Psychotropic medications ===")
        for m in summary.psychotropic_medications:
            print(f"  {m.dispensed_at} · {m.product_name} · {m.ingredient_name} "
                  f"[{m.efficacy_class_name or m.psychotropic_class}] "
                  f"· {m.days_supply}일 · {m.daily_frequency}회/일")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(_cli())
