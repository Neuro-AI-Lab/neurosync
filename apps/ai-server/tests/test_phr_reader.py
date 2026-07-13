"""PHR 파서 pytest 유닛/통합 테스트.

CI (`uv run pytest`)가 자동 수집. `smoke_phr_reader.py`(CLI 재현)와 별도.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.agents.patient_history import PatientHistoryAgent, _safe_date
from src.data.psychotropic_ingredients import classify, is_psychotropic
from src.schemas.phr import PhrLoadInput

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = REPO_ROOT / "docs" / "ai" / "samples" / "phr"


# ── 성분 카탈로그 유닛 테스트 ─────────────────────────────────────────


class TestPsychotropicCatalog:
    def test_ssri_recognized(self):
        assert classify("escitalopram") == "SSRI"
        assert classify("Escitalopram") == "SSRI"  # 대소문자 무관
        assert is_psychotropic("sertraline")

    def test_benzo_recognized(self):
        assert classify("lorazepam") == "BENZO"
        assert classify("alprazolam") == "BENZO"

    def test_zdrug_recognized(self):
        assert classify("zolpidem") == "ZDRUG"

    def test_non_psychiatric(self):
        assert classify("acetaminophen") == "NON_PSYCHIATRIC"
        assert classify("mosapride") == "NON_PSYCHIATRIC"
        assert not is_psychotropic("finasteride")

    def test_empty_and_none(self):
        assert classify(None) == "NON_PSYCHIATRIC"
        assert classify("") == "NON_PSYCHIATRIC"
        assert classify("   ") == "NON_PSYCHIATRIC"


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
    # (has_psychiatric_history, min_meds, min_visits, expected_classes)
    "VP-001": (False, 3, 4, set()),
    "VP-002": (True, 4, 7, {"SSRI"}),
    "VP-003": (True, 3, 6, {"BENZO"}),  # 응급 로라제팜 단회
    "VP-004": (True, 8, 11, {"SSRI", "BENZO", "ZDRUG"}),
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
    assert "SSRI" in note
    assert "BENZO" in note
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
    assert phr["total_medications"] >= 4
    assert isinstance(phr["psychotropic_medications"], list)
    assert phr["psychotropic_medications"][0]["psychotropic_class"] == "SSRI"


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
