"""Tests for `src/services/f5_report.py` — markdown/PDF/FHIR exporters +
`save_f5_result`. `docs/ai/f5_quick_dev_plan.md` §5, §7.2 machine checks
(a)/(d) (section completeness, PDF render sanity)."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pypdf

from src.f5 import (
    ChartFilenames,
    DepartmentCandidateInput,
    DomainInferenceSnapshot,
    F3Administration,
    HandoffReportInput,
    SessionSnapshot,
    assemble_handoff_report,
)
from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput, ScaleSeriesPoint
from src.services.f5_report import build_markdown_report, build_pdf_report, save_f5_result

# All 15 §2.2 section labels a completeness grep expects, never silently
# dropped (design doc §7.2 check (a) / qa's T1-F5-VER-011).
_EXPECTED_SECTION_MARKERS = [
    "## A0.",
    "## A1.",
    "## A2.",
    "## A3.",
    "## A4.",
    "## A5.",
    "## A6.",
    "## A7.",
    "## A8.",
    "## B1.",
    "## B2.",
    "## B3.",
    "## B4.",
    "## B5.",
]


def _full_report():
    session = SessionSnapshot(
        session_id="f1_VP-TEST",
        persona_id="VP-TEST",
        persona_name="김테스트",
        session_index=11,
        simulated_date="2027-01-12",
        model="solar-pro3-260323",
        final_slots={
            "chief_complaint": "잠을 잘 못 자는 것이 가장 신경 쓰임",
            "history_of_present_illness": "3개월 전부터 지속된 수면 문제",
            "risk_assessment": "자살/자해 사고 탐색 질문에 부인",
        },
        session_ctrs=2,
        crisis_triggered=True,
        crisis_turn=5,
        risk_floor=3,
        probe_event_count=2,
    )
    current_f3 = F3Administration(
        session_index=11,
        simulated_date="2027-01-12",
        outcome="no_questionnaire_indicated",
    )
    prior_f3 = F3Administration(
        session_index=9,
        simulated_date="2026-11-12",
        outcome="administered",
        scale_name="PHQ-9",
        item_bank_version="v1",
        item_bank_provenance="v1, verbatim Pfizer PHQ-9",
        responses=(3,) * 9,
        total_score=27,
        max_score=27,
        severity="severe",
        critical_item_positive=True,
        safety_referral=True,
    )
    apd = AIPredictedDiseaseOutput(
        candidates=[
            AIPredictedDiseaseCandidate(
                disease="계절성 정동장애",
                similarity_score=0.485,
                source_id="case_card:1045",
                quote="q1",
            ),
            AIPredictedDiseaseCandidate(
                disease="월경전 불쾌장애",
                similarity_score=0.485,
                source_id="case_card:1045",
                quote="q1",
            ),
        ],
        mode="rag_live",
        recommended_questionnaire="PHQ-9",
    )
    dept = DepartmentCandidateInput(
        department="정신건강의학과", reason="복합 증상", domain_ref="sleep"
    )
    longitudinal = LongitudinalAnalysisOutput(
        vp_id="VP-TEST",
        n_sessions=11,
        ctrs_series=[
            CTRSSeriesPoint(
                session_index=9, simulated_date="2026-11-12", session_ctrs=4, crisis_triggered=False
            ),
            CTRSSeriesPoint(
                session_index=11, simulated_date="2027-01-12", session_ctrs=2, crisis_triggered=True
            ),
        ],
        scale_series={
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=9,
                    simulated_date="2026-11-12",
                    scale_name="PHQ-9",
                    administered=True,
                    total_score=27,
                    max_score=27,
                    severity="severe",
                )
            ]
        },
        overall_direction="worsened",
        concordance_flag="discordant",
        crisis_f3_gaps=[
            "session 11 (2027-01-12): risk-elevated (crisis_triggered=True, session_ctrs=2) but "
            "NO scale was administered this session"
        ],
    )
    inp = HandoffReportInput(
        vp_id="VP-TEST",
        session=session,
        current_session_f3=current_f3,
        all_f3_administrations=(prior_f3, current_f3),
        domain_inference=DomainInferenceSnapshot(
            ai_predicted_disease=apd, department_candidates=(dept,)
        ),
        longitudinal=longitudinal,
        chart_filenames=ChartFilenames(
            scales_ctrs_sentiment="VP-TEST_x_temporal_scales_ctrs_sentiment.png"
        ),
    )
    return assemble_handoff_report(inp)


def _minimal_report():
    """Every optional section absent — the "everything empty" edge case."""
    session = SessionSnapshot(
        session_id="f1_VP-MIN",
        persona_id="VP-MIN",
        persona_name="최소",
        session_index=1,
        simulated_date="2026-01-01",
        model="solar-pro3",
        final_slots={},
        session_ctrs=None,
        crisis_triggered=False,
        crisis_turn=None,
        risk_floor=None,
        probe_event_count=0,
    )
    inp = HandoffReportInput(
        vp_id="VP-MIN",
        session=session,
        current_session_f3=None,
        all_f3_administrations=(),
        domain_inference=DomainInferenceSnapshot(
            ai_predicted_disease=AIPredictedDiseaseOutput(
                candidates=[], mode="experimental_unpopulated"
            )
        ),
        longitudinal=LongitudinalAnalysisOutput(vp_id="VP-MIN", n_sessions=1),
    )
    return assemble_handoff_report(inp)


# ── Markdown ────────────────────────────────────────────────────────────


class TestMarkdownCompleteness:
    def test_all_sections_present_full_report(self) -> None:
        md = build_markdown_report(_full_report())
        for marker in _EXPECTED_SECTION_MARKERS:
            assert marker in md, f"missing section marker {marker}"

    def test_all_sections_present_minimal_report_with_absent_markers(self) -> None:
        """Every section header renders even when the underlying data is
        empty — with an explicit absence marker, never a silently-dropped
        header (design doc §7.2 check (a))."""
        md = build_markdown_report(_minimal_report())
        for marker in _EXPECTED_SECTION_MARKERS:
            assert marker in md, f"missing section marker {marker}"
        assert "정보 없음" in md

    def test_a3_longitudinal_signal_and_staleness_rendered(self) -> None:
        md = build_markdown_report(_full_report())
        assert "종단 위험 신호" in md
        assert "9회차" in md  # staleness pointer references S9
        assert "27" in md

    def test_a5_stale_administering_session_disclosed(self) -> None:
        md = build_markdown_report(_full_report())
        a5_section = md.split("## A5.")[1].split("## A6.")[0]
        assert "administering_session_index | 9" in a5_section
        assert "True" in a5_section  # is_stale_relative_to_header

    def test_a6_tie_marker_rendered(self) -> None:
        md = build_markdown_report(_full_report())
        assert "공동 1위" in md

    def test_a8_absent_marker_when_narrative_disabled(self) -> None:
        md = build_markdown_report(_full_report())
        assert "AI 종합 소견 미생성 (narrative disabled)" in md

    def test_non_validated_caveat_adjacent_to_a5_numbers(self) -> None:
        md = build_markdown_report(_full_report())
        a5_section = md.split("## A5.")[1].split("## A6.")[0]
        assert "검증된 임상 설문 시행이 아닙니다" in a5_section

    def test_no_probability_wording_near_similarity_score(self) -> None:
        """REV-013 §4: `similarity_score` is never AFFIRMATIVELY labeled a
        probability. "확률" may only appear inside the explicit NEGATION
        disclaimer ("...확률...아닙니다") — every line containing it must
        also contain a negation morpheme on the same line."""
        md = build_markdown_report(_full_report())
        a6_section = md.split("## A6.")[1].split("## A7.")[0]
        assert "probability" not in a6_section.lower()
        for line in a6_section.splitlines():
            if "확률" in line:
                assert "아닙니다" in line or "아니" in line, f"unhedged 확률 mention: {line!r}"


# ── PDF (design doc §7.2 check (d)) ─────────────────────────────────────


class TestPdfRenderSanity:
    def test_pdf_nonzero_size_and_at_least_one_page(self) -> None:
        pdf_bytes = build_pdf_report(_full_report())
        assert len(pdf_bytes) > 0
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 1

    def test_pdf_page_scan_via_raw_bytes(self) -> None:
        """Byte-level `/Type /Page` scan, per brief's alternate check
        method (independent of the pypdf dev-dep)."""
        pdf_bytes = build_pdf_report(_full_report())
        assert pdf_bytes.count(b"/Type /Page") >= 1 or pdf_bytes.count(b"/Type/Page") >= 1

    def test_pdf_korean_text_legible_not_garbled(self) -> None:
        pdf_bytes = build_pdf_report(_full_report())
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        for expected in ("비공식", "예상질환", "위험", "인계 요약"):
            assert expected in text, f"expected Korean text {expected!r} not found/garbled"

    def test_pdf_disclaimer_present(self) -> None:
        pdf_bytes = build_pdf_report(_full_report())
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "공식 의무기록" in text

    def test_pdf_minimal_report_still_renders(self) -> None:
        pdf_bytes = build_pdf_report(_minimal_report())
        assert len(pdf_bytes) > 0
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 1

    def test_pdf_embeds_chart_when_path_supplied(self, tmp_path: Path) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        chart_path = tmp_path / "chart.png"
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])
        fig.savefig(chart_path)
        plt.close(fig)

        report = _full_report()
        pdf_with_chart = build_pdf_report(report, {"scales_ctrs_sentiment": chart_path})
        pdf_without_chart = build_pdf_report(report, {})
        assert len(pdf_with_chart) > len(pdf_without_chart)


# ── save_f5_result ────────────────────────────────────────────────────


class TestSaveF5Result:
    def test_writes_three_files_with_expected_naming(self, tmp_path: Path) -> None:
        paths = save_f5_result(_full_report(), tmp_path, vp_id="VP-TEST")
        assert set(paths) == {"markdown", "pdf", "fhir"}
        assert paths["markdown"].name.endswith("_handoff.md")
        assert paths["pdf"].name.endswith("_handoff.pdf")
        assert paths["fhir"].name.endswith("_handoff_fhir.json")
        for p in paths.values():
            assert p.exists()
            assert p.stat().st_size > 0
            assert p.parent == tmp_path / "VP-TEST"

    def test_fhir_json_is_valid_json(self, tmp_path: Path) -> None:
        import json

        paths = save_f5_result(_full_report(), tmp_path, vp_id="VP-TEST")
        data = json.loads(paths["fhir"].read_text(encoding="utf-8"))
        assert data["resourceType"] == "Bundle"

    def test_naming_matches_vp_prefix_pattern(self, tmp_path: Path) -> None:
        paths = save_f5_result(_full_report(), tmp_path, vp_id="VP-TEST")
        pattern = re.compile(r"^VP-TEST_\d{8}_\d{6}_handoff")
        for p in paths.values():
            assert pattern.match(p.stem) or pattern.match(p.name)
