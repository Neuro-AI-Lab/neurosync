"""PHR 파서 pytest 유닛/통합 테스트.

CI (`uv run pytest`)가 자동 수집. `smoke_phr_reader.py`(CLI 재현)와 별도.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.agents.patient_history import PatientHistoryAgent, _safe_date
from src.data import hira_efficacy_cache
from src.data.psychotropic_classification import classify_efficacy, is_psychiatric
from src.schemas.phr import PhrLoadInput

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = REPO_ROOT / "docs" / "ai" / "samples" / "phr"


# ── 약효분류 판정 유닛 테스트 (HIRA 약효분류번호 기반) ────────────────


class TestEfficacyClassification:
    def test_psychoneurotic_117(self):
        # 117 정신신경용제 — 항우울제/항불안제/항정신병약 포괄
        assert classify_efficacy(117) == "PSYCHONEUROTIC"
        assert is_psychiatric("PSYCHONEUROTIC")

    def test_sedative_hypnotic_112(self):
        assert classify_efficacy(112) == "SEDATIVE_HYPNOTIC"
        assert is_psychiatric("SEDATIVE_HYPNOTIC")

    def test_non_psychiatric_codes(self):
        # 114 해열진통, 239 소화기, 214 혈압강하 등은 정신과 아님
        assert classify_efficacy(114) == "NON_PSYCHIATRIC"
        assert classify_efficacy(214) == "NON_PSYCHIATRIC"
        assert not is_psychiatric("NON_PSYCHIATRIC")

    def test_unknown_when_none(self):
        # 약효분류 미조회 → UNKNOWN (정신과로 단정하지 않음)
        assert classify_efficacy(None) == "UNKNOWN"
        assert not is_psychiatric("UNKNOWN")


class TestEfficacyCache:
    """캐시(HIRA API 스냅샷)가 샘플 코드를 authoritative 하게 매핑."""

    def test_escitalopram_code_is_psychoneurotic(self):
        info = hira_efficacy_cache.lookup("474802ATB")
        assert info is not None
        assert info.meft_div_no == 117
        assert info.div_nm == "정신신경용제"

    def test_alprazolam_code_is_psychoneurotic(self):
        # 국내 분류상 항불안제(alprazolam)도 117 정신신경용제
        info = hira_efficacy_cache.lookup("105502ATB")
        assert info is not None and info.meft_div_no == 117

    def test_acetaminophen_code_non_psychiatric(self):
        info = hira_efficacy_cache.lookup("101408ATB")
        assert info is not None
        assert classify_efficacy(info.meft_div_no) == "NON_PSYCHIATRIC"

    def test_cache_miss_returns_none(self):
        assert hira_efficacy_cache.lookup("000000XXX") is None
        assert hira_efficacy_cache.lookup(None) is None


# ── 날짜 파서 유닛 테스트 ─────────────────────────────────────────────


class TestSafeDate:
    def test_iso_date(self):
        d = _safe_date("2026-04-12")
        assert d is not None and d.isoformat() == "2026-04-12"

    def test_iso_datetime(self):
        d = _safe_date("2026-04-12T09:00:00")
        assert d is not None and d.isoformat() == "2026-04-12"

    def test_compact_yyyymmdd(self):
        d = _safe_date("20260412")
        assert d is not None and d.isoformat() == "2026-04-12"

    def test_none_and_empty(self):
        assert _safe_date(None) is None
        assert _safe_date("") is None
        assert _safe_date("   ") is None

    def test_invalid_string(self):
        assert _safe_date("not-a-date") is None


# ── 페르소나별 통합 테스트 ─────────────────────────────────────────────


PERSONA_EXPECTATIONS = {
    # 원본 페르소나 MD 100% 재현 (docs/ai/personas/VP-*.md 기준)
    # 약효분류(HIRA meftDivNo) 기반 판정. escitalopram/sertraline/alprazolam은
    # 모두 117 정신신경용제 → PSYCHONEUROTIC (국내 분류상 항불안제도 117).
    # (has_psychiatric_history, min_meds, min_visits, expected_classes)
    "VP-001": (False, 3, 4, set()),                    # 정신과 이력 없음 · 감기·소화 3건
    "VP-002": (True, 2, 4, {"PSYCHONEUROTIC"}),        # Escitalopram 10mg 2회 재조제
    "VP-003": (False, 3, 6, set()),                    # 정신과 이력 없음 · 고혈압+감기·소화
    "VP-004": (True, 6, 9, {"PSYCHONEUROTIC"}),        # Sertraline→Esc→Alprazolam 전부 117
}


@pytest.mark.parametrize("vp_id", list(PERSONA_EXPECTATIONS.keys()))
def test_persona_summary(vp_id: str):
    """4 페르소나 샘플 PHR을 병합 파싱 · 임상 판정 정합 확인."""
    med_path = SAMPLES_DIR / f"{vp_id}_medications.json"
    vis_path = SAMPLES_DIR / f"{vp_id}_visits.json"
    if not med_path.is_file() or not vis_path.is_file():
        pytest.skip(f"{vp_id} sample missing")

    exp_has, exp_min_meds, exp_min_visits, exp_classes = PERSONA_EXPECTATIONS[vp_id]

    async def _run():
        agent = PatientHistoryAgent()
        return await agent.run(
            PhrLoadInput(
                session_id=f"pytest-{vp_id}",
                bundle_paths=[str(med_path), str(vis_path)],
            )
        )

    summary = asyncio.run(_run())

    classes = {m.psychotropic_class for m in summary.psychotropic_medications}
    assert summary.has_psychiatric_history is exp_has, (
        f"{vp_id}: has_psychiatric_history={summary.has_psychiatric_history}"
    )
    assert summary.total_medication_events >= exp_min_meds, (
        f"{vp_id}: medications={summary.total_medication_events}"
    )
    assert summary.total_visits >= exp_min_visits, (
        f"{vp_id}: visits={summary.total_visits}"
    )
    assert classes == exp_classes, f"{vp_id}: classes={classes}"
    # 계약 자동 필드도 채워짐
    assert summary.latency_ms >= 0.0
    assert summary.reason_summary != ""


def test_summary_prompt_note_negative():
    """정신과 이력 없는 경우 프롬프트 텍스트 확인."""
    med_path = SAMPLES_DIR / "VP-001_medications.json"
    vis_path = SAMPLES_DIR / "VP-001_visits.json"
    if not med_path.is_file():
        pytest.skip("VP-001 sample missing")

    async def _run():
        agent = PatientHistoryAgent()
        summary = await agent.run(
            PhrLoadInput(
                session_id="pytest-note-neg",
                bundle_paths=[str(med_path), str(vis_path)],
            )
        )
        note = agent.to_system_prompt_note(summary)
        return summary, note

    summary, note = asyncio.run(_run())
    assert not summary.has_psychiatric_history
    assert "확인되지 않습니다" in note


def test_summary_prompt_note_positive():
    """정신과 이력 있는 경우 프롬프트에 약물군 · 최근 조제 포함."""
    med_path = SAMPLES_DIR / "VP-004_medications.json"
    vis_path = SAMPLES_DIR / "VP-004_visits.json"
    if not med_path.is_file():
        pytest.skip("VP-004 sample missing")

    async def _run():
        agent = PatientHistoryAgent()
        summary = await agent.run(
            PhrLoadInput(
                session_id="pytest-note-pos",
                bundle_paths=[str(med_path), str(vis_path)],
            )
        )
        note = agent.to_system_prompt_note(summary)
        return summary, note

    summary, note = asyncio.run(_run())
    assert summary.has_psychiatric_history
    # 약효분류 라벨 (VP-004 약물 전부 117 정신신경용제)
    assert "정신신경용제" in note
    assert "최근 조제" in note


def test_handoff_snippet_structure():
    """to_handoff_snippet의 반환 스키마 계약."""
    med_path = SAMPLES_DIR / "VP-002_medications.json"
    vis_path = SAMPLES_DIR / "VP-002_visits.json"
    if not med_path.is_file():
        pytest.skip("VP-002 sample missing")

    async def _run():
        agent = PatientHistoryAgent()
        summary = await agent.run(
            PhrLoadInput(
                session_id="pytest-handoff",
                bundle_paths=[str(med_path), str(vis_path)],
            )
        )
        return agent.to_handoff_snippet(summary)

    snippet = asyncio.run(_run())
    assert "phr" in snippet
    phr = snippet["phr"]
    assert phr["has_psychiatric_history"] is True
    # VP-002: Escitalopram 10mg × 2회 재조제 (원본 6주 이력)
    assert phr["total_medications"] >= 2
    assert isinstance(phr["psychotropic_medications"], list)
    first = phr["psychotropic_medications"][0]
    assert first["psychotropic_class"] == "PSYCHONEUROTIC"
    assert first["efficacy_class_no"] == 117
    assert first["efficacy_class_name"] == "정신신경용제"


def test_first_coding_returns_empty_on_system_mismatch():
    """Bug fix regression: system_hint 매칭 실패 시 다른 system coding으로 오염 방지."""
    from src.agents.patient_history import _first_coding

    node = {
        "coding": [
            {"system": "https://other.system", "code": "OTHER-123", "display": "Other"},
        ]
    }
    # KDCode 힌트인데 실제로는 다른 system만 있음 → 빈 dict 반환해야 함
    assert _first_coding(node, system_hint="kdcode") == {}
    # 힌트 없으면 fallback으로 첫 coding
    assert _first_coding(node)["code"] == "OTHER-123"
    # 매칭되면 그 coding 반환
    node2 = {
        "coding": [
            {"system": "https://other.system", "code": "OTHER-123"},
            {"system": "https://biz.kpis.or.kr/CodeSystem/kdcode", "code": "KD-456"},
        ]
    }
    assert _first_coding(node2, system_hint="kdcode")["code"] == "KD-456"


def test_summarize_warns_on_different_mhid(caplog):
    """Bug fix regression: 여러 파일에 다른 MHID가 있으면 warning 로그."""
    import asyncio
    import logging

    from src.agents.patient_history import PatientHistoryAgent

    def _bundle(mhid: str) -> dict:
        return {
            "publicData": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [
                            {
                                "type": {"coding": [{"code": "MHID"}]},
                                "value": mhid,
                            }
                        ],
                        "name": [{"text": f"person-{mhid}"}],
                    }
                },
            ],
            "medicalData": [],
            "healthData": {},
        }

    async def _run():
        agent = PatientHistoryAgent()
        return await agent.summarize([_bundle("11111111"), _bundle("22222222")])

    with caplog.at_level(logging.WARNING, logger="src.agents.patient_history"):
        summary = asyncio.run(_run())
    assert summary.patient.mhid == "11111111"
    warnings = [r for r in caplog.records if "different MHID" in r.getMessage()]
    assert warnings, "MHID mismatch warning not emitted"


def test_missing_file_returns_empty_summary():
    """존재하지 않는 파일은 스킵 · summary에서 안 나타남 (no exception)."""

    async def _run():
        agent = PatientHistoryAgent()
        return await agent.run(
            PhrLoadInput(
                session_id="pytest-missing",
                bundle_paths=["/tmp/does-not-exist.json"],
            )
        )

    summary = asyncio.run(_run())
    assert summary.total_medication_events == 0
    assert summary.total_visits == 0
    assert not summary.has_psychiatric_history
