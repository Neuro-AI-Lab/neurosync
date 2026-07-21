"""Tests for `src/services/f5_report.py` — markdown/PDF/FHIR exporters +
`save_f5_result`. `_archive/plans/f5_quick_dev_plan.md` §5, §7.2 machine checks
(a)/(d) (section completeness, PDF render sanity).

Readability redesign (this mission — clinician-first hand-off, <2-min read):
markdown/PDF section headers below reflect the NEW structure (핵심요약 →
위험 → 주호소/현병력 → 슬롯표+경과 → 설문 → 종단추세+차트 → AI참고 → 권고 →
각주). `build_fhir_bundle`/`validate_fhir_bundle` are UNCHANGED (still use
the old A0-A8/B1-B5 section titles) — FHIR-facing tests are untouched."""

from __future__ import annotations

import html
import io
import re
from pathlib import Path

import pypdf
import pytest

from src.f5 import (
    ChartFilenames,
    DepartmentCandidateInput,
    DomainInferenceSnapshot,
    F3Administration,
    HandoffReportInput,
    SessionSlotSnapshot,
    SessionSnapshot,
    assemble_handoff_report,
)
from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.longitudinal import (
    CTRSSeriesPoint,
    LongitudinalAnalysisOutput,
    ScaleSeriesPoint,
    TrendVerdict,
)
from src.services.f5_report import (
    build_markdown_report,
    build_narrative_input_text,
    build_pdf_report,
    save_f5_result,
)

# New top-level section markers, in rendering order (binding rule 10:
# 핵심요약 → 위험 → 주호소/현병력 → 슬롯표+경과 → 설문 → 종단추세+차트 →
# AI참고 → 권고 → 각주). 핵심 요약/면책 조항 render as blockquote boxes
# (`> **...**`), never dropped — checked separately below.
_EXPECTED_SECTION_MARKERS = [
    "## 위험/안전 평가",
    "## 주호소 및 현병력",
    "## 전체 세션 요약",
    "## 시행된 설문",
    "## 종단 추세",
    "## AI 참고 정보 (비진단)",
    "## 권장 진료과 및 후속 조치",
    "## 임상 종합 소견",
    "## 상세 부록",
    "## 각주",
]

_LITERAL_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~=])")


def _rendered_literal(markdown: str) -> str:
    return html.unescape(_LITERAL_ESCAPE_RE.sub(r"\1", markdown))


def _full_report(
    *,
    prior_total_score: int = 27,
    prior_max_score: int = 27,
    prior_severity: str = "severe",
    validation_errors_present: bool = False,
    department_candidates: tuple[DepartmentCandidateInput, ...] | None = None,
    apd: AIPredictedDiseaseOutput | None = None,
    all_sessions: tuple[SessionSlotSnapshot, ...] = (),
    narrative_enabled: bool = False,
    narrative_text: str | None = None,
):
    """`prior_total_score`/`prior_max_score`/`prior_severity` default to
    27/27/"severe" (VP-003's real ceiling-score worked example, ADR-038
    Decision 2c) — callers exercising the NO-ceiling path override these
    (e.g. 17/27); every other default is unchanged from this fixture's
    original shape, so `_full_report()` with no args is byte-identical to
    the pre-ADR-038 fixture."""
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
        total_score=prior_total_score,
        max_score=prior_max_score,
        severity=prior_severity,
        critical_item_positive=True,
        safety_referral=True,
    )
    if apd is None:
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
    if department_candidates is None:
        department_candidates = (
            DepartmentCandidateInput(
                department="정신건강의학과", reason="복합 증상", domain_ref="sleep"
            ),
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
                    total_score=prior_total_score,
                    max_score=prior_max_score,
                    severity=prior_severity,
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
            ai_predicted_disease=apd,
            department_candidates=department_candidates,
            validation_errors_present=validation_errors_present,
        ),
        longitudinal=longitudinal,
        chart_filenames=ChartFilenames(
            scales_ctrs_sentiment="VP-TEST_x_temporal_scales_ctrs_sentiment.png"
        ),
        all_sessions=all_sessions,
        narrative_enabled=narrative_enabled,
        narrative_text=narrative_text,
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
        assert "**핵심 요약**" in md
        assert "**면책 조항**" in md

    def test_all_sections_present_minimal_report_with_absent_markers(self) -> None:
        """Every section header renders even when the underlying data is
        empty — with an explicit absence marker, never a silently-dropped
        header (design doc §7.2 check (a))."""
        md = build_markdown_report(_minimal_report())
        for marker in _EXPECTED_SECTION_MARKERS:
            assert marker in md, f"missing section marker {marker}"
        assert "정보 없음" in md

    def test_a3_risk_signals_and_staleness_rendered(self) -> None:
        md = build_markdown_report(_full_report())
        a3_section = md.split("## 위험/안전 평가")[1].split("## 주호소 및 현병력")[0]
        assert "9회차" in a3_section  # staleness pointer references S9
        assert "27" in a3_section

    def test_a5_stale_administering_session_disclosed(self) -> None:
        md = build_markdown_report(_full_report())
        a5_section = md.split("## 시행된 설문")[1].split("## 종단 추세")[0]
        assert "9회차" in a5_section
        assert "[당해 세션 미시행, 직전 시행값]" in a5_section

    def test_a6_tie_marker_rendered(self) -> None:
        md = build_markdown_report(_full_report())
        assert "공동 1위" in md

    def test_a8_absent_marker_when_narrative_disabled(self) -> None:
        md = build_markdown_report(_full_report())
        assert "AI 종합 소견 미생성 (narrative disabled)" in _rendered_literal(md)

    def test_non_validated_caveat_adjacent_to_a5_numbers(self) -> None:
        md = build_markdown_report(_full_report())
        a5_section = md.split("## 시행된 설문")[1].split("## 종단 추세")[0]
        assert "검증된 임상 설문 시행이 아닙니다" in a5_section

    def test_non_validated_caveat_adjacent_to_a3_numbers(self) -> None:
        """EXP-024 check 5c FAIL regression: A3's risk-signal table (S9
        PHQ-9 27/27) AND the staleness-pointer prose (also citing PHQ-9
        27/27) must each carry the caveat, section-local, not only A5/B1.
        `_full_report()`'s prior_f3 (S9, flagged) + current session (S11,
        no F3) exercises both code paths at once."""
        md = build_markdown_report(_full_report())
        a3_section = md.split("## 위험/안전 평가")[1].split("## 주호소 및 현병력")[0]
        signals_block, staleness_block = a3_section.split("최신 시행 척도 안내")
        assert "검증된 임상 설문 시행이 아닙니다" in signals_block, (
            "A3 risk-signal table missing the non-validated-administration caveat"
        )
        assert "검증된 임상 설문 시행이 아닙니다" in staleness_block, (
            "A3 staleness-pointer prose missing the non-validated-administration caveat"
        )

    def test_no_probability_wording_near_similarity_score(self) -> None:
        """REV-013 §4: `similarity_score` is never AFFIRMATIVELY labeled a
        probability. "확률" may only appear inside the explicit NEGATION
        disclaimer ("...확률...아닙니다") — every line containing it must
        also contain a negation morpheme on the same line."""
        md = build_markdown_report(_full_report())
        a6_section = md.split("## AI 참고 정보 (비진단)")[1].split("## 권장 진료과 및 후속 조치")[0]
        assert "probability" not in a6_section.lower()
        for line in a6_section.splitlines():
            if "확률" in line:
                assert "아닙니다" in line or "아니" in line, f"unhedged 확률 mention: {line!r}"

    def test_no_internal_field_names_in_body(self) -> None:
        """Binding rule 1: internal field names / IDs never appear in the
        body — only in the trailing 각주 footnote block, which carries
        only model/generated_at/session_id/item_bank_provenance (none of
        these ID-shaped internal tokens)."""
        md = build_markdown_report(_full_report())
        body = md.split("## 각주")[0]
        for banned in (
            "session_ctrs",
            "risk_floor",
            "probe_event_count",
            "safety_referral",
            "critical_item_positive",
            "is_diagnostic",
        ):
            assert banned not in body, f"internal field name {banned!r} leaked into body"

    def test_no_internal_dimension_labels_in_trend_evidence(self) -> None:
        """Regression guard: F4's own `TrendVerdict.evidence[0]` is
        prefixed `"{label}: "` where `label` is the RAW internal
        dimension name for `session_ctrs`/`slot_fill_count` (confirmed
        via `src/f4.py::_first_last_slope_trend`'s own `label=` call
        sites) — the real VP-001 artifact exposed this because the
        default `_full_report()` fixture leaves `trend_verdicts` empty."""
        report = _full_report()
        report.b_longitudinal.analysis.trend_verdicts = [
            TrendVerdict(
                dimension="session_ctrs",
                direction="unchanged",
                basis="first_vs_last_delta+slope_sign",
                n_comparable_points=2,
                evidence=["session_ctrs: first-vs-last delta session 1->2: 4 -> 4 (+0)"],
            ),
            TrendVerdict(
                dimension="slot_fill_count",
                direction="improved",
                basis="first_vs_last_delta+slope_sign",
                n_comparable_points=2,
                evidence=["slot_fill_count: first-vs-last delta session 1->2: 4 -> 7 (+3)"],
            ),
        ]
        md = build_markdown_report(report)
        body = md.split("## 각주")[0]
        assert "session_ctrs:" not in body
        assert "slot_fill_count:" not in body
        # the underlying numbers must still be present, not dropped
        assert "4 → 4" in body
        assert "4 → 7" in body


class TestSummaryBox:
    def test_summary_box_at_top_before_any_section_marker(self) -> None:
        md = build_markdown_report(_full_report())
        summary_pos = md.index("**핵심 요약**")
        first_section_pos = min(md.index(m) for m in _EXPECTED_SECTION_MARKERS)
        assert summary_pos < first_section_pos

    def test_summary_box_has_risk_flag_and_scale_trend(self) -> None:
        md = build_markdown_report(_full_report())
        box = md.split("**핵심 요약**")[1].split("**면책 조항**")[0]
        assert "위험 플래그" in box
        assert "최신 설문" in box
        assert "PHQ-9" in _rendered_literal(box)

    def test_summary_box_at_most_8_content_lines(self) -> None:
        md = build_markdown_report(_full_report())
        box = md.split("**핵심 요약**")[1].split("**면책 조항**")[0]
        content_lines = [ln for ln in box.splitlines() if ln.strip() not in ("", ">")]
        assert len(content_lines) <= 8

    def test_disclaimer_box_at_most_3_bullets(self) -> None:
        md = build_markdown_report(_full_report())
        box = md.split("**면책 조항**")[1].split("## 위험/안전 평가")[0]
        bullets = [ln for ln in box.splitlines() if ln.strip().startswith(">") and "-" in ln]
        assert len(bullets) <= 3


class TestCtrsStageLabelMapping:
    """CTRS 1=most urgent ... 5=stable (`src.schemas.common.CTRSLevel`).
    The Korean label table must track `CTRS_TO_RISK`'s actual risk
    gradient (critical->high->medium->low->none), NOT the raw enum-member
    comment text — that raw text literally reads "중증/주의" (severe/
    caution) for level 4 even though level 4 maps to `RiskLevel.low`;
    rendering that verbatim would contradict the risk_level shown
    alongside it (conductor-flagged clinical-accuracy fix)."""

    def test_all_5_levels_have_a_label(self) -> None:
        from src.services.f5_report import _CTRS_STAGE_KO

        assert set(_CTRS_STAGE_KO) == {1, 2, 3, 4, 5}

    def test_level_1_and_5_match_specified_wording(self) -> None:
        from src.services.f5_report import _CTRS_STAGE_KO

        assert _CTRS_STAGE_KO[1] == "최긴급 (즉각 개입)"
        assert _CTRS_STAGE_KO[5] == "안정"

    def test_level_4_is_not_labeled_severe_or_caution(self) -> None:
        """Regression guard: level 4 (RiskLevel.low) must never carry
        severe/caution wording, however it is later edited."""
        from src.services.f5_report import _CTRS_STAGE_KO

        assert "중증" not in _CTRS_STAGE_KO[4]
        assert "주의" not in _CTRS_STAGE_KO[4]

    def test_labels_track_ctrs_to_risk_monotonic_gradient(self) -> None:
        """Cross-checks against the actual source of truth
        (`src.schemas.common.CTRS_TO_RISK`) so this table cannot silently
        drift from the enum's own risk mapping."""
        from src.schemas.common import CTRS_TO_RISK, CTRSLevel, RiskLevel
        from src.services.f5_report import _CTRS_STAGE_KO

        risk_rank = {
            RiskLevel.critical: 0,
            RiskLevel.high: 1,
            RiskLevel.medium: 2,
            RiskLevel.low: 3,
            RiskLevel.none: 4,
        }
        ordered = sorted(CTRSLevel, key=lambda lvl: lvl.value)
        ranks = [risk_rank[CTRS_TO_RISK[lvl]] for lvl in ordered]
        assert ranks == sorted(ranks), "CTRS_TO_RISK must stay urgency-descending 1->5"
        for lvl in ordered:
            assert lvl.value in _CTRS_STAGE_KO

    def test_ctrs_stage_ko_helper_renders_level_and_label(self) -> None:
        from src.services.f5_report import _ctrs_stage_ko

        assert _ctrs_stage_ko(4) == "4/5 — 경도 우려 (준안정)"
        assert _ctrs_stage_ko(None) == "미상"


class TestSlotTableExcludesSystemRows:
    def test_system_and_mse_rows_removed_from_slot_table(self) -> None:
        """Binding rule 4: system-only slots (never populated by the
        conversation extractor) and the MSE slot (already covered in its
        own subsection) are removed from the slot table."""
        md = build_markdown_report(_full_report())
        section = md.split("## 전체 세션 요약")[1].split("## 시행된 설문")[0]
        table_block = section.split("**주요 경과**")[0]
        assert "진료 기본정보" not in table_block
        assert "정신상태검사" not in table_block
        assert "평가/진단적 인상" not in table_block
        assert "치료계획/치료내용" not in table_block
        assert "주호소" in table_block  # a real clinical slot stays


class TestChartAbsentMarkers:
    """EXP-024 check 7 finding regression: a missing F4 chart (filename is
    `None`) must render an explicit per-chart absent line, never be
    silently dropped — same explicit-absent-marker discipline as every
    other section. `_full_report()` only sets the `scales_ctrs_sentiment`
    filename, so the other 3 exercise the fix."""

    def test_missing_charts_render_explicit_absent_markers(self) -> None:
        md = build_markdown_report(_full_report())
        chart_section = md.split("### 추세 차트")[1].split("## AI 참고 정보")[0]
        assert "![scales_ctrs_sentiment]" in chart_section  # the present chart still renders
        assert "질환 유사도 차트: 생성되지 않음" in chart_section
        assert "CTRS 확대 차트: 생성되지 않음" in chart_section
        assert "진료과 후보 신뢰도 차트: 생성되지 않음" in chart_section
        # partial presence must NOT trigger the old blanket all-absent marker
        assert "정보 없음 (차트 없음)" not in chart_section

    def test_all_charts_absent_still_shows_blanket_marker_plus_per_chart_lines(self) -> None:
        md = build_markdown_report(_minimal_report())
        chart_section = md.split("### 추세 차트")[1].split("## AI 참고 정보")[0]
        assert "정보 없음 (차트 없음)" in chart_section
        assert "질환 유사도 차트: 생성되지 않음" in chart_section


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
        for expected in ("비공식", "AI 참고 정보", "위험", "인계 요약", "핵심 요약"):
            assert expected in text, f"expected Korean text {expected!r} not found/garbled"

    def test_pdf_disclaimer_present(self) -> None:
        pdf_bytes = build_pdf_report(_full_report())
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "공식 의무기록" in text

    def test_pdf_a3_caveat_present(self) -> None:
        """EXP-024 check 5c FAIL regression, PDF format."""
        pdf_bytes = build_pdf_report(_full_report())
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "검증된 임상 설문 시행이 아닙니다" in text

    def test_pdf_missing_chart_renders_explicit_absent_marker(self) -> None:
        """EXP-024 check 7 finding regression, PDF format."""
        pdf_bytes = build_pdf_report(_full_report())
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "질환 유사도 차트: 생성되지 않음" in text

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
        # <vp>_<date>_<time>_<unique per-run token>_handoff.* (codex P2: the
        # per-run token decouples same-second exports of the same VP).
        pattern = re.compile(r"^VP-TEST_\d{8}_\d{6}_[0-9a-f]{8}_handoff")
        for p in paths.values():
            assert pattern.match(p.stem) or pattern.match(p.name)


# ── Font embedding (ADR-038 Decision 1, BUG-044) ────────────────────────


def _embedded_korean_font_names(pdf_bytes: bytes) -> set[str]:
    """Returns the `/BaseFont` name of every font resource on page 1 whose
    FontDescriptor (direct, or via `/DescendantFonts` for a Type0
    composite) carries an embedded font program (`/FontFile`, `/FontFile2`,
    or `/FontFile3`) — the pypdf-level equivalent of `pdffonts`' `emb=yes`
    column."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    embedded: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        fonts = resources.get("/Font") or {}
        for fref in fonts.values():
            fobj = fref.get_object()
            base_font = str(fobj.get("/BaseFont", ""))
            descriptors = []
            direct_desc = fobj.get("/FontDescriptor")
            if direct_desc is not None:
                descriptors.append(direct_desc.get_object())
            for child_ref in fobj.get("/DescendantFonts") or []:
                child = child_ref.get_object()
                child_desc = child.get("/FontDescriptor")
                if child_desc is not None:
                    descriptors.append(child_desc.get_object())
            for desc in descriptors:
                if any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                    embedded.add(base_font)
    return embedded


class TestPdfFontEmbedding:
    def test_korean_fonts_are_embedded(self) -> None:
        """ADR-038 Decision 1 / BUG-044: the PDF must carry its own Korean
        glyph outlines (emb=yes), not merely reference a CID font NAME the
        consuming viewer is expected to substitute (the old `emb=no`
        failure mode qa's multi-renderer adjudication confirmed breaks on
        a no-CJK-fontconfig host AND under Ghostscript)."""
        pdf_bytes = build_pdf_report(_full_report())
        embedded = _embedded_korean_font_names(pdf_bytes)
        assert embedded, "no embedded font found on page 1 at all"
        assert any("NotoSansCJKkr" in name for name in embedded), embedded
        assert any("NotoSerifCJKkr" in name for name in embedded), embedded

    def test_old_non_embedded_cid_font_names_absent(self) -> None:
        """Raster-independent regression guard: the old `ADR-037` Decision
        7 CID font names must never appear anywhere in the PDF bytes —
        proves the font choice was actually replaced, not merely
        supplemented."""
        pdf_bytes = build_pdf_report(_full_report())
        assert b"HYGothic-Medium" not in pdf_bytes
        assert b"HYSMyeongJo-Medium" not in pdf_bytes

    def test_middle_dot_and_warning_glyph_extract_correctly(self) -> None:
        """Content-integrity companion to the embedding check: `·`/`⚠`
        (BUG-044's 2 tofu-glyph targets) still round-trip through the
        text layer -- this does NOT by itself prove the RASTER renders
        correctly (that needs a rasterizer, verified manually this
        dispatch, see HANDOFF evidence), but confirms embedding did not
        regress content fidelity."""
        pdf_bytes = build_pdf_report(_full_report())
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "·" in text
        assert "⚠" in text

    def test_register_korean_fonts_raises_on_missing_asset(self, monkeypatch, tmp_path) -> None:
        """ADR-038 Decision 1: a missing font asset must raise a clear,
        named error -- NEVER silently fall back to the old CID fonts."""
        import src.services.f5_report as f5_report_module

        monkeypatch.setattr(f5_report_module, "_BODY_FONT_PATH", tmp_path / "does-not-exist.ttf")
        # Force re-registration (module-level registry is process-global).
        monkeypatch.setattr(f5_report_module, "_BODY_FONT", "test-missing-body-font")
        with pytest.raises(RuntimeError, match="ADR-038"):
            f5_report_module._register_korean_fonts()

    def test_register_korean_fonts_raises_on_sha256_mismatch(self, monkeypatch, tmp_path) -> None:
        """ADR-038 Decision 1: a font asset present but content-mismatched
        against the pinned SHA256 must also raise loudly, not silently
        register a swapped/corrupted font."""
        import src.services.f5_report as f5_report_module

        tampered = tmp_path / "tampered.ttf"
        tampered.write_bytes(b"not a real font file")
        monkeypatch.setattr(f5_report_module, "_BODY_FONT_PATH", tampered)
        monkeypatch.setattr(f5_report_module, "_BODY_FONT", "test-tampered-body-font")
        with pytest.raises(RuntimeError, match="SHA256"):
            f5_report_module._register_korean_fonts()


# ── A7 validation-drop disclosure, exporter-level (ADR-038 Decision 2a) ──


class TestA7DisclosureExporters:
    def test_markdown_shows_validation_dropped_wording_when_flagged(self) -> None:
        """CVR-026 Finding 5 (major): the internal bug-ticket ID
        (`VAL-016/BUG-031`) must NOT appear inline in the clinician-facing
        A7 body — only the honest, ID-free Korean plain-text note there;
        the ID-bearing original moves to the 각주 시스템 참고 subsection
        (never dropped, verified via the whole-document `md` search
        below)."""
        from src.schemas.handoff_report import A7_NO_CANDIDATES_VALIDATION_DROPPED_KO
        from src.services.f5_report import _A7_ABSENCE_VALIDATION_DROPPED_PLAIN_KO

        report = _full_report(department_candidates=(), validation_errors_present=True)
        md = build_markdown_report(report)
        a7_section = md.split("## 권장 진료과 및 후속 조치")[1].split("## 임상 종합 소견")[0]
        assert _A7_ABSENCE_VALIDATION_DROPPED_PLAIN_KO in _rendered_literal(a7_section)
        assert A7_NO_CANDIDATES_VALIDATION_DROPPED_KO not in a7_section
        assert "VAL-016" not in a7_section
        # relocated, not dropped — the full original + ID lives in the
        # 각주 시스템 참고 subsection of the SAME document.
        assert A7_NO_CANDIDATES_VALIDATION_DROPPED_KO in _rendered_literal(md)
        assert "VAL-016" in _rendered_literal(md.split("## 각주")[1])

    def test_markdown_shows_model_judged_wording_when_not_flagged(self) -> None:
        from src.schemas.handoff_report import (
            A7_NO_CANDIDATES_MODEL_JUDGED_KO,
            A7_NO_CANDIDATES_VALIDATION_DROPPED_KO,
        )

        report = _full_report(department_candidates=(), validation_errors_present=False)
        md = build_markdown_report(report)
        a7_section = md.split("## 권장 진료과 및 후속 조치")[1].split("## 임상 종합 소견")[0]
        assert A7_NO_CANDIDATES_MODEL_JUDGED_KO in _rendered_literal(a7_section)
        assert A7_NO_CANDIDATES_VALIDATION_DROPPED_KO not in a7_section

    def test_pdf_shows_validation_dropped_wording_when_flagged(self) -> None:
        from src.schemas.handoff_report import A7_NO_CANDIDATES_VALIDATION_DROPPED_KO

        report = _full_report(department_candidates=(), validation_errors_present=True)
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "VAL-016" in text
        assert A7_NO_CANDIDATES_VALIDATION_DROPPED_KO[:20] in text

    def test_non_empty_candidates_never_shows_absence_wording(self) -> None:
        report = _full_report(validation_errors_present=True)  # default has 1 dept candidate
        md = build_markdown_report(report)
        a7_section = md.split("## 권장 진료과 및 후속 조치")[1].split("## 임상 종합 소견")[0]
        assert "정보 없음" not in a7_section


# ── A6 reason_summary surfacing, exporter-level (ADR-038 Decision 2b) ────


class TestA6ReasonSummaryExporters:
    def test_markdown_surfaces_reason_summary_when_unpopulated(self) -> None:
        """CVR-026 Finding 4 (major): an unrecognized English
        `reason_summary` (this fixture's ad-hoc string, not the real
        `src.f2` production wording) must render as the generic Korean
        fallback in the clinician-facing A6 body — never raw English —
        with the original relocated to the 각주 시스템 참고 subsection
        (never dropped)."""
        from src.services.f5_report import _A6_REASON_SUMMARY_FALLBACK_KO

        apd = AIPredictedDiseaseOutput(
            candidates=[],
            mode="experimental_unpopulated",
            reason_summary="no RAG chunks retrieved this run",
        )
        report = _full_report(apd=apd)
        md = build_markdown_report(report)
        a6_section = md.split("## AI 참고 정보 (비진단)")[1].split("## 권장 진료과 및 후속 조치")[0]
        assert "no RAG chunks retrieved this run" not in a6_section
        assert _A6_REASON_SUMMARY_FALLBACK_KO in _rendered_literal(a6_section)
        assert "mode: experimental_unpopulated" in _rendered_literal(a6_section)
        assert "no RAG chunks retrieved this run" in md.split("## 각주")[1]

    def test_markdown_translates_known_production_reason_summary(self) -> None:
        """The REAL `src.f2` unpopulated-mode wording is a known, exact
        mapping — translated to plain Korean directly in the body, no
        English leak."""
        apd = AIPredictedDiseaseOutput(
            candidates=[],
            mode="experimental_unpopulated",
            reason_summary=(
                "Stage 1 ran in llm_only mode (no RAG chunks retrieved this run) — the "
                "AI-disease container has no chunk-derived evidence to populate from"
            ),
        )
        report = _full_report(apd=apd)
        md = build_markdown_report(report)
        a6_section = md.split("## AI 참고 정보 (비진단)")[1].split("## 권장 진료과 및 후속 조치")[0]
        assert "Stage 1 ran in llm_only mode" not in a6_section
        assert "RAG" in a6_section  # plain-Korean translation still names RAG

    def test_pdf_surfaces_reason_summary_when_unpopulated(self) -> None:
        apd = AIPredictedDiseaseOutput(
            candidates=[],
            mode="experimental_unpopulated",
            reason_summary="no RAG chunks retrieved this run",
        )
        report = _full_report(apd=apd)
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        # relocated to the PDF's own 시스템 참고 footnote, not the A6 box —
        # still present somewhere in the full document (audit trail).
        assert "no RAG chunks retrieved this run" in text

    def test_markdown_omits_reason_summary_for_rag_live_empty(self) -> None:
        apd = AIPredictedDiseaseOutput(
            candidates=[], mode="rag_live", reason_summary="should not appear"
        )
        report = _full_report(apd=apd)
        md = build_markdown_report(report)
        a6_section = md.split("## AI 참고 정보 (비진단)")[1].split("## 권장 진료과 및 후속 조치")[0]
        assert "should not appear" not in a6_section


class TestA6TopThreeAndFootnote:
    """Binding rule 8: top 3 candidates in the body, the rest compacted
    into a footnote line."""

    def test_more_than_3_candidates_splits_top3_and_rest(self) -> None:
        apd = AIPredictedDiseaseOutput(
            candidates=[
                AIPredictedDiseaseCandidate(
                    disease=f"질환{i}", similarity_score=0.5 - i * 0.01, source_id=f"c:{i}"
                )
                for i in range(5)
            ],
            mode="rag_live",
        )
        report = _full_report(apd=apd)
        md = build_markdown_report(report)
        a6_section = md.split("## AI 참고 정보 (비진단)")[1].split("## 권장 진료과 및 후속 조치")[0]
        assert "질환0" in a6_section and "질환2" in a6_section
        assert "기타 후보" in a6_section
        assert "질환3" in a6_section and "질환4" in a6_section


# ── Exact-ceiling caveat co-location, exporter-level (ADR-038 Decision 2c) ──


class TestCeilingCaveatExporters:
    def test_markdown_a3_and_a5_show_caveat_adjacent_on_ceiling_score(self) -> None:
        from src.schemas.handoff_report import CEILING_SCORE_CAVEAT_KO

        report = _full_report(prior_total_score=27, prior_max_score=27)
        md = build_markdown_report(report)
        a3_section = md.split("## 위험/안전 평가")[1].split("## 주호소 및 현병력")[0]
        a5_section = md.split("## 시행된 설문")[1].split("## 종단 추세")[0]
        assert CEILING_SCORE_CAVEAT_KO in _rendered_literal(a3_section)
        assert CEILING_SCORE_CAVEAT_KO in _rendered_literal(a5_section)
        # adjacency: the caveat must sit on the same 27/27 line's table/note,
        # not merely appear anywhere in the whole document -- already
        # implied by the section-scoped assertions above, plus explicit
        # score co-occurrence:
        assert "27/27" in a3_section
        assert "27" in a5_section

    def test_markdown_no_new_caveat_below_ceiling(self) -> None:
        """17/27 (below scale ceiling) must NOT trigger the A3/A5 caveat
        insertions -- no near-ceiling logic (ADR-038 explicitly scopes this
        out); the top-level 핵심요약/면책 boxes never repeat this caveat
        either (binding rule 3: disclaimer stays a fixed 3-line box)."""
        from src.schemas.handoff_report import CEILING_SCORE_CAVEAT_KO

        report = _full_report(
            prior_total_score=17, prior_max_score=27, prior_severity="moderately_severe"
        )
        md = build_markdown_report(report)
        a3_section = md.split("## 위험/안전 평가")[1].split("## 주호소 및 현병력")[0]
        a5_section = md.split("## 시행된 설문")[1].split("## 종단 추세")[0]
        assert CEILING_SCORE_CAVEAT_KO not in a3_section
        assert CEILING_SCORE_CAVEAT_KO not in a5_section
        assert CEILING_SCORE_CAVEAT_KO not in md

    def test_pdf_shows_caveat_on_ceiling_score(self) -> None:
        report = _full_report(prior_total_score=27, prior_max_score=27)
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        # A3 (risk table adjacency) + A5 (questionnaire section) each carry
        # the full caveat once — the compact table cell only adds "· 만점".
        assert text.count("ISS-F2V-028") >= 2

    def test_pdf_caveat_absent_below_ceiling(self) -> None:
        report = _full_report(
            prior_total_score=17, prior_max_score=27, prior_severity="moderately_severe"
        )
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert text.count("ISS-F2V-028") == 0


# ── VP-004-shaped renderer polish: caveat consolidation + absent-session
# rows (conductor output review of VP-004's EXP-027 handoff.md) ──────────


def _vp004_shaped_report():
    """Reproduces VP-004's (EXP-027) real 10-session risk-table shape: item-9
    positive/near-ceiling PHQ-9 in sessions 1,3,4,5,7,8,9 (26-27/27), a
    LOWER PHQ-9 in session 2/10 (not near-ceiling), and session 6 running a
    DIFFERENT scale (GAD-7, no item-9 concept, never flagged) -- the exact
    shape that previously produced 7 near-identical ceiling-caveat lines and
    silently skipped session 6 in the risk table (5 -> 7)."""
    session = SessionSnapshot(
        session_id="f1_VP-004",
        persona_id="VP-004",
        persona_name="최하은",
        session_index=10,
        simulated_date="2027-01-15",
        model="solar-pro3-260323",
        final_slots={"risk_assessment": "자살사고 부인(탐색 완료)"},
        session_ctrs=2,
        crisis_triggered=True,
        crisis_turn=3,
        risk_floor=2,
        probe_event_count=1,
    )
    near_ceiling_scores = {1: 26, 3: 26, 4: 27, 5: 26, 7: 26, 8: 26, 9: 27}
    admins = []
    ctrs_points = []
    scale_series_phq9 = []
    for idx in range(1, 11):
        date = f"2026-{7 + (idx - 1) // 4:02d}-{(idx * 3) % 28 + 1:02d}"
        ctrs_points.append(
            CTRSSeriesPoint(session_index=idx, simulated_date=date, session_ctrs=3)
        )
        if idx == 6:
            admins.append(
                F3Administration(
                    session_index=idx,
                    simulated_date=date,
                    outcome="administered",
                    scale_name="GAD-7",
                    responses=(3,) * 7,
                    total_score=21,
                    max_score=21,
                    severity="severe",
                    critical_item_positive=False,
                    safety_referral=False,
                )
            )
            continue
        score = near_ceiling_scores.get(idx, 20)
        admins.append(
            F3Administration(
                session_index=idx,
                simulated_date=date,
                outcome="administered",
                scale_name="PHQ-9",
                responses=(3,) * 9,
                total_score=score,
                max_score=27,
                severity="severe",
                critical_item_positive=idx in near_ceiling_scores,
                safety_referral=idx in near_ceiling_scores,
            )
        )
        scale_series_phq9.append(
            ScaleSeriesPoint(
                session_index=idx,
                simulated_date=date,
                scale_name="PHQ-9",
                administered=True,
                total_score=score,
                max_score=27,
                severity="severe",
                critical_item_positive=idx in near_ceiling_scores,
            )
        )
    session6_date = next(p.simulated_date for p in ctrs_points if p.session_index == 6)
    longitudinal = LongitudinalAnalysisOutput(
        vp_id="VP-004",
        n_sessions=10,
        ctrs_series=ctrs_points,
        scale_series={
            "PHQ-9": scale_series_phq9,
            "GAD-7": [
                ScaleSeriesPoint(
                    session_index=6,
                    simulated_date=session6_date,
                    scale_name="GAD-7",
                    administered=True,
                    total_score=21,
                    max_score=21,
                    severity="severe",
                    critical_item_positive=False,
                )
            ],
        },
        overall_direction="worsened",
        concordance_flag="discordant",
    )
    current_f3 = next(a for a in admins if a.session_index == 10)
    inp = HandoffReportInput(
        vp_id="VP-004",
        session=session,
        current_session_f3=current_f3,
        all_f3_administrations=tuple(admins),
        domain_inference=DomainInferenceSnapshot(
            ai_predicted_disease=AIPredictedDiseaseOutput(
                candidates=[], mode="experimental_unpopulated"
            )
        ),
        longitudinal=longitudinal,
    )
    return assemble_handoff_report(inp)


class TestRiskTableRendererPolish:
    def test_ceiling_caveat_consolidated_to_one_line(self) -> None:
        """7 near-ceiling sessions (1,3,4,5,7,8,9) must produce exactly ONE
        consolidated caveat line naming every affected session, not 7
        near-identical repeated lines."""
        from src.schemas.handoff_report import CEILING_SCORE_CAVEAT_KO

        md = build_markdown_report(_vp004_shaped_report())
        a3_section = md.split("## 위험/안전 평가")[1].split("## 주호소 및 현병력")[0]
        assert _rendered_literal(a3_section).count("ISS-F2V-028") == 1
        assert _rendered_literal(a3_section).count(CEILING_SCORE_CAVEAT_KO) == 1
        consolidated_line = next(
            _rendered_literal(line)
            for line in a3_section.splitlines()
            if "ISS-F2V-028" in _rendered_literal(line)
        )
        for idx in (1, 3, 4, 5, 7, 8, 9):
            assert str(idx) in consolidated_line.split("]")[0], (
                f"session {idx} missing from consolidated caveat line: {consolidated_line}"
            )
        # per-row "· 만점" table marker is untouched
        assert a3_section.count("· 만점") == 7  # sessions 1,3,4,5,7,8 (26/27) + 9 (27/27)

    def test_absent_session_rendered_as_explicit_row_not_silent_gap(self) -> None:
        """Session 6 (administered GAD-7, never item-9-flagged) must appear
        as its OWN table row, never a silent jump from 5 to 7."""
        md = build_markdown_report(_vp004_shaped_report())
        a3_section = md.split("## 위험/안전 평가")[1].split("## 주호소 및 현병력")[0]
        table_lines = [
            line
            for line in a3_section.splitlines()
            if line.startswith("| ") and not line.startswith("| 세션") and "---" not in line
        ]
        session_ids = [line.split("|")[1].strip() for line in table_lines]
        assert session_ids == [str(i) for i in range(1, 11)], session_ids
        row6 = next(line for line in table_lines if line.split("|")[1].strip() == "6")
        cells = [c.strip() for c in row6.split("|")]
        # | <blank> | 6 | date | score | item9 | verdict | <blank> |
        assert cells[3] == "미시행"
        assert _rendered_literal(cells[4]) == "-"
        assert "GAD-7" in _rendered_literal(cells[5])

    def test_pdf_absent_session_row_present(self) -> None:
        pdf_bytes = build_pdf_report(_vp004_shaped_report())
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "GAD-7" in text
        assert text.count("ISS-F2V-028") == 1


# ── All-session slot overview exporters (Task 1) ────────────────────────

_SLOT_SESSIONS = (
    SessionSlotSnapshot(9, "2026-11-12", {"chief_complaint": "3개월 전부터 지속된 수면 문제"}),
    SessionSlotSnapshot(
        11, "2027-01-12", {"chief_complaint": "잠을 잘 못 자는 것이 가장 신경 쓰임"}
    ),
)


class TestSlotOverviewExporters:
    def test_markdown_section_present_with_table_and_caveat(self) -> None:
        report = _full_report(all_sessions=_SLOT_SESSIONS)
        md = build_markdown_report(report)
        section = md.split("## 전체 세션 요약")[1].split("## 시행된 설문")[0]
        assert "임상의의 직접 평가나 검증된 척도 시행이 아닙니다" in section
        assert "주호소" in section
        assert "잠을 잘 못 자는 것이 가장 신경 쓰임" in section
        assert "미수집" in section  # e.g. medical_history, never populated

    def test_markdown_major_course_bullets_rendered(self) -> None:
        report = _full_report(all_sessions=_SLOT_SESSIONS)
        md = build_markdown_report(report)
        section = md.split("## 전체 세션 요약")[1].split("## 시행된 설문")[0]
        assert "주요 경과" in section
        assert "S9: '3개월 전부터 지속된 수면 문제'" in section
        assert "S11: '잠을 잘 못 자는 것이 가장 신경 쓰임'" in section

    def test_markdown_section_pointer_rendered(self) -> None:
        report = _full_report(all_sessions=_SLOT_SESSIONS)
        md = build_markdown_report(report)
        section = md.split("## 전체 세션 요약")[1].split("## 시행된 설문")[0]
        assert "A2 참조" in section  # HPI slot's pointer

    def test_pdf_slot_overview_table_present(self) -> None:
        report = _full_report(all_sessions=_SLOT_SESSIONS)
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "전체 세션 요약" in text
        assert "미수집" in text


# ── A8 opt-in narrative exporters (Task 2, handoff_generator v3) ────────


class TestNarrativeOptInExporters:
    def test_markdown_renders_enabled_label_and_text(self) -> None:
        report = _full_report(
            narrative_enabled=True, narrative_text="환자는 수면 문제를 자가보고함."
        )
        md = build_markdown_report(report)
        a8_section = md.split("## 임상 종합 소견")[1].split("## 각주")[0]
        assert "AI 생성 — 임상 진단 아님" in a8_section
        assert "환자는 수면 문제를 자가보고함." in _rendered_literal(a8_section)
        assert "AI 종합 소견 미생성" not in a8_section

    def test_markdown_disabled_still_shows_absent_marker(self) -> None:
        md = build_markdown_report(_full_report())
        a8_section = md.split("## 임상 종합 소견")[1].split("## 각주")[0]
        assert "AI 종합 소견 미생성 (narrative disabled)" in _rendered_literal(a8_section)

    def test_pdf_renders_enabled_label_and_text(self) -> None:
        report = _full_report(
            narrative_enabled=True, narrative_text="환자는 수면 문제를 자가보고함."
        )
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "환자는 수면 문제를 자가보고함." in text
        assert "AI 생성" in text


class TestBuildNarrativeInputText:
    def test_excludes_a6_disease_names(self) -> None:
        """The narrative-generation LLM call must never even RECEIVE
        disease-candidate text (strongest defense against an A6->A8 leak,
        on top of `f5.py::_build_a8`'s own output-side guard)."""
        report = _full_report()  # default apd has "계절성 정동장애"/"월경전 불쾌장애"
        text = build_narrative_input_text(report)
        assert "계절성 정동장애" not in text
        assert "월경전 불쾌장애" not in text

    def test_includes_a1_a2_a3_a5_a7_b_summary_fields(self) -> None:
        report = _full_report(all_sessions=_SLOT_SESSIONS)
        text = build_narrative_input_text(report)
        assert "세션:" in text
        assert "CTRS:" in text
        assert "주호소:" in text
        assert "현병력:" in text
        assert "위험 평가 존재 여부:" in text
        assert "정신상태 메모:" in text
        assert "시행된 설문:" in text
        assert "권장 진료과:" in text
        assert "종단 추세:" in text


# ── CVR-026 fix verification (this mission) ──────────────────────────────


class TestDetailAppendix:
    """Finding 1 (blocking): every truncation marker must point to a REAL,
    numbered 상세 부록 entry — never the old dead `"(상세 아래)"` reference."""

    def test_truncated_risk_quote_gets_numbered_appendix_entry(self) -> None:
        report = _full_report()
        long_quote = "환자 발화: " + "가" * 150
        report.a3_risk_safety.risk_assessment_text = long_quote
        md = build_markdown_report(report)
        assert "(상세 아래)" not in md
        assert "(상세 부록 1 참조)" in _rendered_literal(md)
        appendix = md.split("## 상세 부록")[1].split("## 각주")[0]
        assert long_quote in appendix

    def test_truncated_slot_value_gets_appendix_entry(self) -> None:
        long_value = "개" * 120
        sessions = (
            SessionSlotSnapshot(1, "2026-01-01", {"personal_social_history": long_value}),
            SessionSlotSnapshot(2, "2026-02-01", {"personal_social_history": long_value}),
        )
        report = _full_report(all_sessions=sessions)
        md = build_markdown_report(report)
        assert "(상세 아래)" not in md
        appendix = md.split("## 상세 부록")[1].split("## 각주")[0]
        assert long_value in appendix

    def test_minimal_report_appendix_shows_explicit_absence(self) -> None:
        md = build_markdown_report(_minimal_report())
        appendix = md.split("## 상세 부록")[1].split("## 각주")[0]
        assert "해당 없음" in appendix

    def test_pdf_appendix_section_present_with_full_text(self) -> None:
        report = _full_report()
        long_quote = "환자 발화: " + "가" * 150
        report.a3_risk_safety.risk_assessment_text = long_quote
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "상세 부록" in text
        assert "위험평가 발화 원문" in text
        # reportlab's own line-wrap inserts newlines pypdf's text layer
        # reproduces — compare with whitespace collapsed, not verbatim.
        assert long_quote.replace(" ", "") in text.replace("\n", "").replace(" ", "")


class TestSlotHistoryFullAppendix:
    """Finding 2 (major): the compact slot table's per-entry 60-char cap on
    `change_history` loses clinically material text (an A1-A3 style
    appendix regression) — the FULL, untruncated quotes now always live in
    a dedicated 상세 부록 subsection, pointed to from the table."""

    def test_full_change_history_quotes_appear_in_appendix_not_table(self) -> None:
        long_value_1 = "짧은값1" * 20
        long_value_2 = "짧은값2" * 20
        sessions = (
            SessionSlotSnapshot(1, "2026-01-01", {"chief_complaint": long_value_1}),
            SessionSlotSnapshot(2, "2026-02-01", {"chief_complaint": long_value_2}),
        )
        report = _full_report(all_sessions=sessions)
        md = build_markdown_report(report)
        table_section = md.split("## 전체 세션 요약")[1].split("**주요 경과**")[0]
        appendix_section = md.split("## 상세 부록")[1].split("## 각주")[0]
        assert "상세 부록 참조" in table_section
        assert long_value_1 not in table_section  # compact cell stays truncated
        assert long_value_1 in appendix_section
        assert long_value_2 in appendix_section


class TestMajorCourseBulletsMaterialMiddle:
    """Finding 3 (major): a first/last-only selection can silently elide a
    clinically material EARLY signal into the "..." placeholder — the
    bullet now surfaces a real MIDDLE change point too."""

    def test_selects_first_material_middle_and_last_not_ellipsis(self) -> None:
        sessions = tuple(
            SessionSlotSnapshot(i, f"2026-0{i}-01", {"history_of_present_illness": f"값{i}"})
            for i in range(1, 6)
        )
        report = _full_report(all_sessions=sessions)
        md = build_markdown_report(report)
        section = md.split("## 전체 세션 요약")[1].split("## 시행된 설문")[0]
        assert "→ ... →" not in section
        assert "S1: '값1'" in section
        assert "S3: '값3'" in section  # material middle point, not elided
        assert "S5: '값5'" in section


class TestInternalRefStrippingAndDedup:
    """Findings 5-8: internal review/bug-ID citations relocate to the 각주
    시스템 참고 subsection; the near-duplicate F3-gap/ceiling caveats
    collapse to one canonical body location."""

    def test_gap_disclosure_bullet_strips_review_id_suffix(self) -> None:
        report = _full_report()
        report.a5_questionnaires.gap_disclosure = [
            "session 10 (2026-12-12): risk-elevated (crisis_triggered=True, session_ctrs=2) but "
            "NO scale was administered this session — F3 gap at a clinically high-value point "
            "(CVR-020 Finding 4 / binding condition 3)"
        ]
        md = build_markdown_report(report)
        body = md.split("## 각주")[0]
        assert "CVR-020" not in body
        assert "binding condition" not in body
        footnote = md.split("## 각주")[1]
        assert "CVR-020" in _rendered_literal(footnote)

    def test_gap_acuity_framing_note_has_no_review_id_in_body(self) -> None:
        from src.schemas.handoff_report import CRISIS_F3_GAP_ACUITY_FRAMING_KO

        md = build_markdown_report(_full_report())
        body = md.split("## 각주")[0]
        assert "CVR-022" not in body
        assert CRISIS_F3_GAP_ACUITY_FRAMING_KO not in body

    def test_ceiling_caveat_not_repeated_verbatim_within_a3(self) -> None:
        from src.schemas.handoff_report import CEILING_SCORE_CAVEAT_KO

        report = _full_report(prior_total_score=27, prior_max_score=27)
        md = build_markdown_report(report)
        a3_section = md.split("## 위험/안전 평가")[1].split("## 주호소 및 현병력")[0]
        assert _rendered_literal(a3_section).count(CEILING_SCORE_CAVEAT_KO) == 1

    def test_pdf_ceiling_caveat_not_repeated_within_a3(self) -> None:
        report = _full_report(prior_total_score=27, prior_max_score=27)
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        # A3 contributes exactly 1 occurrence (table-adjacent), A5 its own
        # separate ADR-038 Decision 2c occurrence -> total 2, not 3+.
        assert text.count("ISS-F2V-028") == 2


class TestMarkdownInjectionHardening:
    """Round-1 review blocker: clinical text must not forge md structure."""

    _ACTIVE_LINK_OR_IMAGE = re.compile(r"(?<!\\)!?(?<!\\)\[[^\n]*?(?<!\\)\]\([^\n)]*\)")

    @staticmethod
    def _unescaped_pipe_count(row: str) -> int:
        return len(re.findall(r"(?<!\\)\|", row))

    @staticmethod
    def _adversarial_report(**kw):
        session = SessionSnapshot(
            session_id="f1_VP-INJ",
            persona_id="VP-INJ",
            persona_name="주입검증",
            session_index=1,
            simulated_date="2026-01-01",
            model="solar-pro3",
            final_slots={
                "chief_complaint": "무기력 <script>alert(1)</script>",
                "history_of_present_illness": "수면 문제\n\n## 위조된 진료 지시\n복약 중단",
                "family_history": "약물A | 약물B | 약물C | 약물D | 약물E",
            },
            session_ctrs=3,
            crisis_triggered=False,
            crisis_turn=None,
            risk_floor=None,
            probe_event_count=0,
        )
        inp = HandoffReportInput(
            vp_id="VP-INJ",
            session=session,
            current_session_f3=None,
            all_f3_administrations=(),
            domain_inference=DomainInferenceSnapshot(
                ai_predicted_disease=AIPredictedDiseaseOutput(
                    candidates=[], mode="experimental_unpopulated"
                )
            ),
            longitudinal=LongitudinalAnalysisOutput(vp_id="VP-INJ", n_sessions=1),
            **kw,
        )
        return assemble_handoff_report(inp)

    def test_clinical_text_cannot_forge_headings(self) -> None:
        md = build_markdown_report(self._adversarial_report())
        assert not any(line.startswith("## 위조된") for line in md.splitlines())

    def test_raw_html_is_neutralized(self) -> None:
        md = build_markdown_report(self._adversarial_report())
        assert "<script>" not in md

    def test_pipes_in_slot_values_do_not_break_table_rows(self) -> None:
        md = build_markdown_report(self._adversarial_report())
        row = next(
            line for line in md.splitlines() if "약물A" in line and line.startswith("|")
        )
        assert row.count("|") - row.count("\\|") == 6, f"table row broken: {row!r}"

    def test_narrative_cannot_forge_headings(self) -> None:
        md = build_markdown_report(
            self._adversarial_report(
                narrative_enabled=True,
                narrative_text="정상 요약 문장.\n## 가짜 소견 섹션",
            )
        )
        assert not any(line.startswith("## 가짜") for line in md.splitlines())

    def test_md_block_neutralizes_setext_fences_lists_and_links(self) -> None:
        # codex P2: Setext (===), fences (```/~~~), ordered lists (1./1)),
        # blockquotes/tables and the inline-link seam ]( must ALL be escaped so
        # opt-in narrative text cannot forge report structure.
        import re

        from src.services.f5_report import _md_block

        raw = (
            "제목\n===\n```\ncode\n```\n~~~\n1. 항목\n2) 항목\n> 인용\n"
            "| a | b |\n[클릭](http://evil)"
        )
        out = _md_block(raw)
        for line in out.splitlines():
            assert not re.match(
                r"^\s*(#|>|\||=|~|`|[-+*]\s|\d+[.)]\s)", line
            ), f"active markdown line survived: {line!r}"
        assert "](" not in out, "inline-link seam must be broken"

    def test_literal_escapers_normalize_lines_and_escape_all_markdown_punctuation(self) -> None:
        # Given
        from src.services.f5_report import _md_block, _md_inline

        punctuation = r"\`*_{}[]()#+-.!|~="

        # When
        inline = _md_inline(f"left\r\n right {punctuation}")
        block = _md_block(f"line1\r\nline2\rline3 {punctuation}")

        # Then
        assert "\r" not in inline + block
        assert "\n" not in inline
        assert block.count("\n") == 2
        escaped_punctuation = r"\\\`\*\_\{\}\[\]\(\)\#\+\-\.\!\|\~\="
        assert inline.endswith(escaped_punctuation)
        assert block.endswith(escaped_punctuation)

    def test_inline_clinical_links_and_images_remain_literal_data(self) -> None:
        # Given
        report = self._adversarial_report()
        report.a1_chief_complaint.text = "증상 [inlinelink](https://example.invalid/a)"
        report.a2_hpi.text = "관찰 ![inlineimage](https://example.invalid/i.png)"

        # When
        section = build_markdown_report(report).split("## 주호소 및 현병력")[1].split(
            "## 전체 세션 요약"
        )[0]

        # Then
        assert "inlinelink" in section and "inlineimage" in section
        assert self._ACTIVE_LINK_OR_IMAGE.search(section) is None

    def test_a6_candidate_fields_cannot_create_links_images_or_table_cells(self) -> None:
        # Given
        report = _full_report()
        candidate = report.a6_ai_predicted_disease.candidates[0]
        candidate.tie_marker = "[rank](https://example.invalid/r) | forged"
        candidate.candidate.disease = "![disease](https://example.invalid/d.png) | forged"
        report.a6_ai_predicted_disease.disclaimer = "<b>notice</b> [policy](https://invalid)"
        report.a6_ai_predicted_disease.recommended_questionnaire = "![survey](https://invalid/i)"
        report.a6_ai_predicted_disease.recommendation_caveat = "[caveat](https://invalid/c)"

        # When
        section = build_markdown_report(report).split("## AI 참고 정보 (비진단)")[1].split(
            "## 권장 진료과 및 후속 조치"
        )[0]
        candidate_row = next(line for line in section.splitlines() if "disease" in line)

        # Then
        assert all(token in section for token in ("rank", "disease", "notice", "survey", "caveat"))
        assert self._ACTIVE_LINK_OR_IMAGE.search(section) is None
        assert self._unescaped_pipe_count(candidate_row) == 4
        assert "<b>" not in section

    def test_a7_department_and_reason_cannot_create_links_images_or_table_cells(self) -> None:
        # Given
        report = _full_report(
            department_candidates=(
                DepartmentCandidateInput(
                    department="[clinic](https://example.invalid/c) | forged",
                    reason="![reason](https://example.invalid/r.png) | forged",
                    domain_ref="sleep",
                ),
            )
        )

        # When
        section = build_markdown_report(report).split("## 권장 진료과 및 후속 조치")[1].split(
            "## 임상 종합 소견"
        )[0]
        candidate_row = next(line for line in section.splitlines() if "clinic" in line)

        # Then
        assert "clinic" in section and "reason" in section
        assert self._ACTIVE_LINK_OR_IMAGE.search(section) is None
        assert self._unescaped_pipe_count(candidate_row) == 3

    def test_model_session_and_item_provenance_are_literal_metadata(self) -> None:
        # Given
        report = _full_report()
        report.a0_header.model = "[model](https://example.invalid/m)"
        report.a0_header.session_id = "![session](https://example.invalid/s.png)"
        report.generated_at = "[generated](https://example.invalid/g)"
        report.a5_questionnaires.item_bank_provenance = "![bank](https://example.invalid/b.png)"

        # When
        footnotes = build_markdown_report(report).split("## 각주")[1]

        # Then
        assert all(token in footnotes for token in ("model", "session", "generated", "bank"))
        assert self._ACTIVE_LINK_OR_IMAGE.search(footnotes) is None

    def test_appendix_and_longitudinal_evidence_preserve_data_without_structure(self) -> None:
        # Given
        report = _full_report()
        payload = "[evidence](https://example.invalid/e) | ![plot](https://invalid/p.png)"
        row = next(row for row in report.slot_overview.rows if row.key == "chief_complaint")
        row.latest_value = f"{payload} " * 8
        row.change_history_full = [f"early {payload}", f"late {payload}"]
        report.b_longitudinal.analysis.trend_verdicts = [
            TrendVerdict(
                dimension=f"dimension {payload}",
                direction="worsened",
                basis="fixture",
                n_comparable_points=2,
                evidence=[f"dimension {payload}: {payload}"],
            )
        ]

        # When
        markdown = build_markdown_report(report)
        trend = markdown.split("## 종단 추세")[1].split("### 추세 차트")[0]
        appendix = markdown.split("## 상세 부록")[1].split("## 각주")[0]
        trend_row = next(line for line in trend.splitlines() if "dimension" in line)

        # Then
        assert "evidence" in trend and "evidence" in appendix
        assert self._ACTIVE_LINK_OR_IMAGE.search(trend + appendix) is None
        assert self._unescaped_pipe_count(trend_row) == 4
        assert not any(
            line.startswith(("# evidence", "> evidence")) for line in appendix.splitlines()
        )

    def test_unsafe_chart_filename_renders_absence_instead_of_image(self) -> None:
        # Given
        report = _full_report()
        report.b_longitudinal.chart_filenames.scales_ctrs_sentiment = (
            "../escape.png)\n## forged\n![remote](https://example.invalid/x.png)"
        )

        # When
        chart_section = build_markdown_report(report).split("### 추세 차트")[1].split(
            "## AI 참고 정보"
        )[0]

        # Then
        assert "척도·CTRS·감성 추이 차트: 생성되지 않음" in chart_section
        assert "scales_ctrs_sentiment" not in chart_section
        assert self._ACTIVE_LINK_OR_IMAGE.search(chart_section) is None


class TestPdfRobustnessAndExporterIsolation:
    """Round-1 review blocker: newline-dense values abort PDF generation
    (reportlab LayoutError in unsplittable cells) and one exporter failure
    suppressed every subsequent artifact."""

    def test_newline_dense_narrative_still_renders_pdf(self) -> None:
        bomb = "무기력" + ("\n" * 79) + "호소"
        report = _full_report(narrative_enabled=True, narrative_text=bomb)
        pdf = build_pdf_report(report, {})
        assert pdf.startswith(b"%PDF")

    def test_pdf_failure_does_not_suppress_fhir_and_markdown(
        self, tmp_path, monkeypatch
    ) -> None:
        import src.services.f5_report as f5r

        def _boom(report, chart_paths):
            raise RuntimeError("simulated PDF failure")

        monkeypatch.setattr(f5r, "build_pdf_report", _boom)
        paths = save_f5_result(_minimal_report(), tmp_path)
        assert "markdown" in paths and paths["markdown"].exists()
        assert "fhir" in paths and paths["fhir"].exists()
        assert "pdf" not in paths

    def test_pdf_line_chunks_preserve_all_content(self) -> None:
        # codex P2: long free text must be PAGINATED, never truncated — every
        # line survives across the returned chunks (no omission marker).
        from src.services.f5_report import _PDF_PARAGRAPH_MAX_LINES, _pdf_line_chunks

        lines = [f"line-{i}" for i in range(_PDF_PARAGRAPH_MAX_LINES * 3 + 7)]
        chunks = _pdf_line_chunks("\n".join(lines))
        assert len(chunks) > 1, "long text must split into multiple flowables"
        assert all(len(c) <= _PDF_PARAGRAPH_MAX_LINES for c in chunks)
        assert [ln for c in chunks for ln in c] == lines, "no line may be dropped or reordered"

    def test_long_narrative_content_survives_in_pdf(self) -> None:
        # codex P2: the LAST line of a >40-line narrative must appear in the
        # rendered PDF (previously truncated with "… (이하 생략)").
        import io

        import pypdf

        sentinel = "LASTLINE1234"
        body = "\n".join(f"finding {i}" for i in range(60)) + f"\n{sentinel}"
        report = _full_report(narrative_enabled=True, narrative_text=body)
        pdf = build_pdf_report(report, {})
        assert pdf.startswith(b"%PDF")
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        text = "".join(page.extract_text() for page in reader.pages)
        assert sentinel in text.replace(" ", ""), "later narrative content was dropped from PDF"
        assert "이하 생략" not in text, "PDF must paginate, not truncate with an omission marker"

    def test_failed_export_does_not_delete_a_prior_valid_pdf(self, tmp_path, monkeypatch) -> None:
        # codex P2: unique per-run prefixes decouple rapid exports of the same
        # VP, so a later FAILED export never deletes an earlier run's valid PDF
        # (nor leaves a stale PDF paired with mismatched md/FHIR).
        import src.services.f5_report as f5r

        report = _minimal_report()
        first = save_f5_result(report, tmp_path)
        assert "pdf" in first and first["pdf"].exists()

        def _boom(report, chart_paths):
            raise RuntimeError("simulated PDF failure")

        monkeypatch.setattr(f5r, "build_pdf_report", _boom)
        second = save_f5_result(report, tmp_path)
        assert "pdf" not in second, "a failed export must not report a PDF path"
        assert first["markdown"] != second["markdown"], "each run must get a unique prefix"
        assert first["pdf"].exists(), "a prior run's valid PDF must survive a later failed export"
        assert second["markdown"].exists() and second["fhir"].exists()

    def test_pdf_does_not_double_escape_clinical_text(self) -> None:
        # codex P2: clinical text containing < or | must render as real
        # characters in the PDF (reportlab's own P() does the escaping), NOT as
        # literal Markdown-escape artifacts &lt; / \|. The shared render helpers
        # hand the PDF RAW text via _pdf_raw instead of Markdown-escaping it.
        import io

        import pypdf

        report = TestMarkdownInjectionHardening._adversarial_report()
        pdf = build_pdf_report(report, {})
        assert pdf.startswith(b"%PDF")
        text = "".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf)).pages)
        assert "&lt;" not in text, "PDF double-escaped '<' as the literal artifact &lt;"
        assert "\\|" not in text, "PDF rendered a literal Markdown pipe-escape \\|"
