"""Tests for `src/services/f5_report.py` — markdown/PDF/FHIR exporters +
`save_f5_result`. `docs/ai/f5_quick_dev_plan.md` §5, §7.2 machine checks
(a)/(d) (section completeness, PDF render sanity)."""

from __future__ import annotations

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
from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput, ScaleSeriesPoint
from src.services.f5_report import (
    build_markdown_report,
    build_narrative_input_text,
    build_pdf_report,
    save_f5_result,
)

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

    def test_non_validated_caveat_adjacent_to_a3_numbers(self) -> None:
        """EXP-024 check 5c FAIL regression: A3's 종단위험신호 table (S9
        PHQ-9 27/27) AND the staleness-pointer prose (also citing PHQ-9
        27/27) must each carry the caveat, section-local, not only A5/B1.
        `_full_report()`'s prior_f3 (S9, flagged) + current session (S11,
        no F3) exercises both code paths at once."""
        md = build_markdown_report(_full_report())
        a3_section = md.split("## A3.")[1].split("## A4.")[0]
        signals_block, staleness_block = a3_section.split("최신성 안내 (staleness pointer)")
        assert "검증된 임상 설문 시행이 아닙니다" in signals_block, (
            "A3 종단위험신호 subsection missing the non-validated-administration caveat"
        )
        assert "검증된 임상 설문 시행이 아닙니다" in staleness_block, (
            "A3 staleness-pointer prose missing the non-validated-administration caveat"
        )

    def test_document_disclaimer_scopes_to_a3_as_well_as_a5_b1(self) -> None:
        """The document-level disclaimer must no longer self-declare its
        questionnaire-score scope as A5/B1-only (EXP-024 check 5c root
        cause) now that A3 also renders scored numbers."""
        md = build_markdown_report(_full_report())
        assert "설문(A3/A5/B1)" in md
        assert "설문(A5/B1)" not in md

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


class TestChartAbsentMarkers:
    """EXP-024 check 7 finding regression: a missing F4 chart (filename is
    `None`) must render an explicit per-chart absent line, never be
    silently dropped — same explicit-absent-marker discipline as every
    other section (A1/A2/A4/A5/A6/A7). `_full_report()` only sets the
    `scales_ctrs_sentiment` filename, so the other 3 exercise the fix."""

    def test_missing_charts_render_explicit_absent_markers(self) -> None:
        md = build_markdown_report(_full_report())
        b5_section = md.split("## B5.")[1]
        assert "![scales_ctrs_sentiment]" in b5_section  # the one present chart still renders
        assert "질환 유사도 차트: 생성되지 않음" in b5_section
        assert "CTRS 확대 차트: 생성되지 않음" in b5_section
        assert "진료과 후보 신뢰도 차트: 생성되지 않음" in b5_section
        # partial presence must NOT trigger the old blanket all-absent marker
        assert "정보 없음 (차트 없음)" not in b5_section

    def test_all_charts_absent_still_shows_blanket_marker_plus_per_chart_lines(self) -> None:
        md = build_markdown_report(_minimal_report())
        b5_section = md.split("## B5.")[1]
        assert "정보 없음 (차트 없음)" in b5_section
        assert "질환 유사도 차트: 생성되지 않음" in b5_section


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
        pattern = re.compile(r"^VP-TEST_\d{8}_\d{6}_handoff")
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

        monkeypatch.setattr(
            f5_report_module, "_BODY_FONT_PATH", tmp_path / "does-not-exist.ttf"
        )
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
        from src.schemas.handoff_report import A7_NO_CANDIDATES_VALIDATION_DROPPED_KO

        report = _full_report(department_candidates=(), validation_errors_present=True)
        md = build_markdown_report(report)
        a7_section = md.split("## A7.")[1].split("## A8.")[0]
        assert A7_NO_CANDIDATES_VALIDATION_DROPPED_KO in a7_section
        assert "VAL-016" in a7_section

    def test_markdown_shows_model_judged_wording_when_not_flagged(self) -> None:
        from src.schemas.handoff_report import (
            A7_NO_CANDIDATES_MODEL_JUDGED_KO,
            A7_NO_CANDIDATES_VALIDATION_DROPPED_KO,
        )

        report = _full_report(department_candidates=(), validation_errors_present=False)
        md = build_markdown_report(report)
        a7_section = md.split("## A7.")[1].split("## A8.")[0]
        assert A7_NO_CANDIDATES_MODEL_JUDGED_KO in a7_section
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
        a7_section = md.split("## A7.")[1].split("## A8.")[0]
        assert "정보 없음" not in a7_section


# ── A6 reason_summary surfacing, exporter-level (ADR-038 Decision 2b) ────


class TestA6ReasonSummaryExporters:
    def test_markdown_surfaces_reason_summary_when_unpopulated(self) -> None:
        apd = AIPredictedDiseaseOutput(
            candidates=[],
            mode="experimental_unpopulated",
            reason_summary="no RAG chunks retrieved this run",
        )
        report = _full_report(apd=apd)
        md = build_markdown_report(report)
        a6_section = md.split("## A6.")[1].split("## A7.")[0]
        assert "no RAG chunks retrieved this run" in a6_section
        assert "mode: experimental_unpopulated" in a6_section

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
        assert "no RAG chunks retrieved this run" in text

    def test_markdown_omits_reason_summary_for_rag_live_empty(self) -> None:
        apd = AIPredictedDiseaseOutput(
            candidates=[], mode="rag_live", reason_summary="should not appear"
        )
        report = _full_report(apd=apd)
        md = build_markdown_report(report)
        a6_section = md.split("## A6.")[1].split("## A7.")[0]
        assert "should not appear" not in a6_section


# ── Exact-ceiling caveat co-location, exporter-level (ADR-038 Decision 2c) ──


class TestCeilingCaveatExporters:
    def test_markdown_a3_and_a5_show_caveat_adjacent_on_ceiling_score(self) -> None:
        from src.schemas.handoff_report import CEILING_SCORE_CAVEAT_KO

        report = _full_report(prior_total_score=27, prior_max_score=27)
        md = build_markdown_report(report)
        a3_section = md.split("## A3.")[1].split("## A4.")[0]
        a5_section = md.split("## A5.")[1].split("## A6.")[0]
        assert CEILING_SCORE_CAVEAT_KO in a3_section
        assert CEILING_SCORE_CAVEAT_KO in a5_section
        # adjacency: the caveat must sit on the same 27/27 line's table/note,
        # not merely appear anywhere in the whole document -- already
        # implied by the section-scoped assertions above, plus explicit
        # score co-occurrence:
        assert "27/27" in a3_section
        assert "27" in a5_section

    def test_markdown_no_new_caveat_below_ceiling(self) -> None:
        """17/27 (below scale ceiling) must NOT trigger the new A3/A5
        caveat insertions -- the pre-existing B1 occurrence is the only one
        (no near-ceiling logic, ADR-038 explicitly scopes this out)."""
        from src.schemas.handoff_report import CEILING_SCORE_CAVEAT_KO

        report = _full_report(
            prior_total_score=17, prior_max_score=27, prior_severity="moderately_severe"
        )
        md = build_markdown_report(report)
        a3_section = md.split("## A3.")[1].split("## A4.")[0]
        a5_section = md.split("## A5.")[1].split("## A6.")[0]
        assert CEILING_SCORE_CAVEAT_KO not in a3_section
        assert CEILING_SCORE_CAVEAT_KO not in a5_section
        # B1's own pre-existing occurrence must still be present (unaffected).
        b1_section = md.split("## B1.")[1].split("## B2.")[0]
        assert CEILING_SCORE_CAVEAT_KO in b1_section

    def test_pdf_shows_caveat_on_ceiling_score(self) -> None:
        """`ISS-F2V-028` (not the full sentence): reportlab's Paragraph
        line-wrapping inserts `\\n` into pypdf's extracted text at wrap
        points, which can fall inside a long sentence -- same short-
        distinctive-substring discipline `test_pdf_a3_caveat_present`
        already uses above, not a weakened check."""
        report = _full_report(prior_total_score=27, prior_max_score=27)
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert text.count("ISS-F2V-028") >= 4  # B1 (pre-existing) + A3 x2 + A5

    def test_pdf_caveat_absent_below_ceiling_except_b1(self) -> None:
        report = _full_report(
            prior_total_score=17, prior_max_score=27, prior_severity="moderately_severe"
        )
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        # exactly 1 occurrence (B1's own pre-existing disclaimer sentence)
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
        section = md.split("## A1-A2 확장.")[1].split("## A3.")[0]
        assert "임상의의 직접 평가나 검증된 척도 시행이 아닙니다" in section
        assert "주호소" in section
        assert "잠을 잘 못 자는 것이 가장 신경 쓰임" in section
        assert "S9:" in section and "S11:" in section
        assert "미수집" in section  # e.g. treatment_plan, never populated

    def test_markdown_section_pointer_rendered(self) -> None:
        report = _full_report(all_sessions=_SLOT_SESSIONS)
        md = build_markdown_report(report)
        section = md.split("## A1-A2 확장.")[1].split("## A3.")[0]
        assert "A1 참조" in section

    def test_pdf_slot_overview_table_present(self) -> None:
        report = _full_report(all_sessions=_SLOT_SESSIONS)
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(p.extract_text() for p in reader.pages)
        assert "전체 세션 슬롯 요약" in text
        assert "미수집" in text


# ── A8 opt-in narrative exporters (Task 2, handoff_generator v3) ────────


class TestNarrativeOptInExporters:
    def test_markdown_renders_enabled_label_and_text(self) -> None:
        report = _full_report(
            narrative_enabled=True, narrative_text="환자는 수면 문제를 자가보고함."
        )
        md = build_markdown_report(report)
        a8_section = md.split("## A8.")[1].split("## B1.")[0]
        assert "AI 생성 — 임상 진단 아님" in a8_section
        assert "환자는 수면 문제를 자가보고함." in a8_section
        assert "AI 종합 소견 미생성" not in a8_section

    def test_markdown_disabled_still_shows_absent_marker(self) -> None:
        md = build_markdown_report(_full_report())
        a8_section = md.split("## A8.")[1].split("## B1.")[0]
        assert "AI 종합 소견 미생성 (narrative disabled)" in a8_section

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
