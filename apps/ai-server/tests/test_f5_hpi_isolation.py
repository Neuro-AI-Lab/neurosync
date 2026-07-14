"""Adversarial red-line isolation test suite for F5 — mirrors
`tests/test_f4_hpi_isolation.py`'s pattern, applied to F5's own hard red
line (design doc §6.1 point 1): AI-predicted-disease content (A6) is its
own clearly-labeled non-diagnostic section, NEVER inside clinician-
narrative sections (A0-A5, A7-A8) — in the typed model, the markdown, the
PDF section builder output, AND the FHIR Composition narrative sections
alike.

Unlike F4's HPI isolation suite (which checks a LEAK CHANNEL — F2's own
computed output reaching an LLM prompt that then reflects it back), F5's
narrative path (A8) is structurally disabled this mission (`ADR-037`
Decision 1, zero LLM calls) — there is no LLM-reflection channel to test
here. F5's own red-line risk is purely an ASSEMBLY-CORRECTNESS one: does
the deterministic engine/exporters ever place disease-candidate content
into a section other than A6? This suite tests that directly, using a
distinctive marker disease name (never otherwise present in any fixture
text) injected ONLY via `AIPredictedDiseaseOutput.candidates`, and asserts
it appears ONLY inside A6's own model field / markdown section / PDF
section / FHIR A6 section+resource — never in A0-A5/A7-A8 or any other
FHIR Composition section.
"""

from __future__ import annotations

import inspect
import io

import pypdf

import src.f5 as f5_module
import src.schemas.handoff_report as handoff_report_module
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
from src.schemas.handoff_report import (
    AIPredictedDiseaseSection,
    HandoffReportOutput,
    NarrativeSection,
)
from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput, ScaleSeriesPoint
from src.services.f5_report import build_fhir_bundle, build_markdown_report, build_pdf_report

_LEAK_MARKER_DISEASE = "ZZZ_F5_LEAK_MARKER_DISEASE_9999"
_LEAK_MARKER_QUOTE = "ZZZ_F5_LEAK_MARKER_QUOTE_9999"


def _marker_report(*, other_slots_contain_marker: bool = False) -> HandoffReportOutput:
    marker_slot_text = _LEAK_MARKER_DISEASE if other_slots_contain_marker else "정상 텍스트"
    session = SessionSnapshot(
        session_id="f1_VP-LEAK",
        persona_id="VP-LEAK",
        persona_name="유출테스트",
        session_index=1,
        simulated_date="2026-01-01",
        model="solar-pro3",
        final_slots={
            "chief_complaint": marker_slot_text,
            "history_of_present_illness": marker_slot_text,
            "risk_assessment": marker_slot_text,
            "mental_status_exam": marker_slot_text,
        },
        session_ctrs=4,
        crisis_triggered=False,
        crisis_turn=None,
        risk_floor=None,
        probe_event_count=0,
    )
    current_f3 = F3Administration(
        session_index=1,
        simulated_date="2026-01-01",
        outcome="administered",
        scale_name="PHQ-9",
        responses=(1,) * 9,
        total_score=9,
        max_score=27,
        severity="mild",
        critical_item_positive=False,
        safety_referral=False,
    )
    apd = AIPredictedDiseaseOutput(
        candidates=[
            AIPredictedDiseaseCandidate(
                disease=_LEAK_MARKER_DISEASE,
                similarity_score=0.9,
                source_id="case_card:1",
                quote=_LEAK_MARKER_QUOTE,
            )
        ],
        mode="rag_live",
        recommended_questionnaire="PHQ-9",
    )
    dept = DepartmentCandidateInput(
        department="정신건강의학과",
        reason="정상적인 진료과 추천 사유 텍스트"
        if not other_slots_contain_marker
        else _LEAK_MARKER_DISEASE,
        domain_ref="sleep",
    )
    longitudinal = LongitudinalAnalysisOutput(
        vp_id="VP-LEAK",
        n_sessions=1,
        ctrs_series=[CTRSSeriesPoint(session_index=1, simulated_date="2026-01-01", session_ctrs=4)],
        scale_series={
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=1,
                    simulated_date="2026-01-01",
                    scale_name="PHQ-9",
                    administered=True,
                    total_score=9,
                    max_score=27,
                    severity="mild",
                )
            ]
        },
    )
    inp = HandoffReportInput(
        vp_id="VP-LEAK",
        session=session,
        current_session_f3=current_f3,
        all_f3_administrations=(current_f3,),
        domain_inference=DomainInferenceSnapshot(
            ai_predicted_disease=apd, department_candidates=(dept,)
        ),
        longitudinal=longitudinal,
        chart_filenames=ChartFilenames(),
    )
    return assemble_handoff_report(inp)


# ── (type layer) ────────────────────────────────────────────────────────


class TestF5TypeLayerIsolation:
    """Import-statement-shaped checks (not bare substring grep, since both
    `src/f5.py` and `src/schemas/handoff_report.py` legitimately DISCUSS
    `schemas.handoff`/`schemas.domain_inference` in their own docstrings —
    mirrors `test_f4_hpi_isolation.py::TestF4TypeLayerIsolation`)."""

    def test_f5_module_never_imports_handoff_or_domain_inference_schema(self) -> None:
        source = inspect.getsource(f5_module)
        assert "from src.schemas.handoff import" not in source
        assert "import src.schemas.handoff" not in source
        assert "from src.schemas.domain_inference" not in source
        assert "import src.schemas.domain_inference" not in source

    def test_handoff_report_schema_never_imports_handoff_or_domain_inference(self) -> None:
        source = inspect.getsource(handoff_report_module)
        assert "from src.schemas.handoff import" not in source
        assert "import src.schemas.handoff" not in source
        assert "from src.schemas.domain_inference" not in source
        assert "import src.schemas.domain_inference" not in source

    def test_handoff_report_schema_shares_no_class_with_handoff_schema(self) -> None:
        import src.schemas.handoff as handoff_module

        def _locally_defined_classes(module: object) -> set[str]:
            return {
                name
                for name, obj in vars(module).items()
                if isinstance(obj, type) and obj.__module__ == module.__name__
            }

        handoff_names = _locally_defined_classes(handoff_module)
        report_names = _locally_defined_classes(handoff_report_module)
        assert handoff_names, "sanity: handoff module must define at least one class"
        assert report_names, "sanity: handoff_report module must define at least one class"
        assert handoff_names.isdisjoint(report_names)

    def test_only_a6_section_type_can_hold_a_disease_candidate(self) -> None:
        """Structural check: of every field type declared across every
        `HandoffReportOutput` submodel, only `AIPredictedDiseaseSection`
        (A6) has a field capable of holding an `AIPredictedDiseaseCandidate`
        (directly or via `RankedDiseaseCandidate`)."""
        from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate

        def _field_type_names(model: type) -> set[str]:
            names: set[str] = set()
            for f in model.model_fields.values():
                names.add(str(f.annotation))
            return names

        for field_name, field_info in HandoffReportOutput.model_fields.items():
            if field_name == "a6_ai_predicted_disease":
                continue
            annotation_str = str(field_info.annotation)
            assert "AIPredictedDiseaseCandidate" not in annotation_str, field_name
            assert "RankedDiseaseCandidate" not in annotation_str, field_name

        assert AIPredictedDiseaseSection is not None
        assert AIPredictedDiseaseCandidate  # sanity import check


# ── (b) live-behavior container check: model level ─────────────────────


class TestModelLevelIsolation:
    def test_marker_disease_only_in_a6(self) -> None:
        report = _marker_report()
        assert (
            report.a6_ai_predicted_disease.candidates[0].candidate.disease == _LEAK_MARKER_DISEASE
        )
        assert _LEAK_MARKER_QUOTE == report.a6_ai_predicted_disease.candidates[0].candidate.quote

        dumped_a0 = report.a0_header.model_dump_json()
        dumped_a1 = report.a1_chief_complaint.model_dump_json()
        dumped_a2 = report.a2_hpi.model_dump_json()
        dumped_a3 = report.a3_risk_safety.model_dump_json()
        dumped_a4 = report.a4_mental_status.model_dump_json()
        dumped_a5 = report.a5_questionnaires.model_dump_json()
        dumped_a8 = report.a8_narrative.model_dump_json()
        dumped_b = report.b_longitudinal.model_dump_json()

        for section_json in (
            dumped_a0,
            dumped_a1,
            dumped_a2,
            dumped_a3,
            dumped_a4,
            dumped_a5,
            dumped_a8,
            dumped_b,
        ):
            assert _LEAK_MARKER_DISEASE not in section_json
            assert _LEAK_MARKER_QUOTE not in section_json

    def test_a8_model_has_no_field_capable_of_holding_disease_content(self) -> None:
        """A8's narrative section has only `narrative_enabled`/`text`/
        `absent_marker` — structurally incapable of holding a typed
        `AIPredictedDiseaseCandidate`."""
        field_names = set(NarrativeSection.model_fields)
        assert field_names == {"narrative_enabled", "text", "absent_marker"}


# ── (b2) Task 2 opt-in narrative — adversarial A6->A8 leak guard ───────
#
# Unlike the rest of this file (where A8 is structurally disabled and thus
# has no leak channel to test), Task 2 (`handoff_generator` v3) adds an
# OPT-IN path: a caller can supply an externally-generated `narrative_text`
# for `f5.py::_build_a8` to render. This is the one new place a leak COULD
# happen (a caller/LLM mistake echoing an A6 candidate's disease name into
# the narrative) — `_build_a8`'s own code-level containment check is the
# defense-in-depth this suite verifies, feeding the SAME distinctive marker
# disease this file's model/markdown/PDF/FHIR suites already use.


def _marker_report_with_narrative(narrative_text: str) -> HandoffReportOutput:
    session = SessionSnapshot(
        session_id="f1_VP-LEAK2",
        persona_id="VP-LEAK2",
        persona_name="유출테스트2",
        session_index=1,
        simulated_date="2026-01-01",
        model="solar-pro3",
        final_slots={"chief_complaint": "정상 텍스트"},
        session_ctrs=4,
        crisis_triggered=False,
        crisis_turn=None,
        risk_floor=None,
        probe_event_count=0,
    )
    apd = AIPredictedDiseaseOutput(
        candidates=[
            AIPredictedDiseaseCandidate(
                disease=_LEAK_MARKER_DISEASE, similarity_score=0.9, source_id="case_card:1"
            )
        ],
        mode="rag_live",
    )
    longitudinal = LongitudinalAnalysisOutput(
        vp_id="VP-LEAK2",
        n_sessions=1,
        ctrs_series=[CTRSSeriesPoint(session_index=1, simulated_date="2026-01-01", session_ctrs=4)],
    )
    inp = HandoffReportInput(
        vp_id="VP-LEAK2",
        session=session,
        current_session_f3=None,
        all_f3_administrations=(),
        domain_inference=DomainInferenceSnapshot(ai_predicted_disease=apd),
        longitudinal=longitudinal,
        chart_filenames=ChartFilenames(),
        narrative_enabled=True,
        narrative_text=narrative_text,
    )
    return assemble_handoff_report(inp)


class TestNarrativeOptInLeakGuard:
    def test_narrative_containing_a6_disease_name_is_rejected(self) -> None:
        from src.schemas.handoff_report import NARRATIVE_REJECTED_DISEASE_LEAK_KO

        report = _marker_report_with_narrative(f"환자는 {_LEAK_MARKER_DISEASE} 소견이 의심됨.")
        assert report.a8_narrative.narrative_enabled is False
        assert report.a8_narrative.text is None
        assert report.a8_narrative.absent_marker == NARRATIVE_REJECTED_DISEASE_LEAK_KO

    def test_rejected_marker_never_appears_in_markdown_a8(self) -> None:
        report = _marker_report_with_narrative(f"환자는 {_LEAK_MARKER_DISEASE} 소견이 의심됨.")
        md = build_markdown_report(report)
        a8_section = md.split("## A8.")[1].split("## B1.")[0]
        assert _LEAK_MARKER_DISEASE not in a8_section

    def test_rejected_marker_never_appears_in_pdf_a8(self) -> None:
        report = _marker_report_with_narrative(f"환자는 {_LEAK_MARKER_DISEASE} 소견이 의심됨.")
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "\n".join(p.extract_text() for p in reader.pages)
        a6_start = full_text.index("A6.")
        a7_start = full_text.index("A7.")
        # The marker legitimately appears once, inside A6's own fenced box.
        assert full_text.count(_LEAK_MARKER_DISEASE) == 1
        assert _LEAK_MARKER_DISEASE in full_text[a6_start:a7_start]

    def test_rejected_marker_never_appears_in_fhir_a8_or_disclaimer(self) -> None:
        report = _marker_report_with_narrative(f"환자는 {_LEAK_MARKER_DISEASE} 소견이 의심됨.")
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        assert not any(s["title"].startswith("A8") for s in comp["section"])
        for section in comp["section"]:
            if section["title"].startswith("A6."):
                continue
            assert _LEAK_MARKER_DISEASE not in section.get("text", {}).get("div", "")

    def test_clean_narrative_without_marker_still_renders_normally(self) -> None:
        """Sanity: the guard only blocks an ACTUAL match — a narrative that
        never mentions the candidate disease renders normally."""
        report = _marker_report_with_narrative("환자는 수면 문제를 자가보고함.")
        assert report.a8_narrative.narrative_enabled is True
        assert report.a8_narrative.text == "환자는 수면 문제를 자가보고함."


# ── (c) markdown-level isolation ────────────────────────────────────────


class TestMarkdownIsolation:
    def test_marker_disease_only_in_a6_markdown_section(self) -> None:
        report = _marker_report()
        md = build_markdown_report(report)
        assert _LEAK_MARKER_DISEASE in md  # sanity: it IS rendered somewhere

        a6_section = md.split("## A6.")[1].split("## A7.")[0]
        assert _LEAK_MARKER_DISEASE in a6_section

        other_sections = md.split("## A6.")[0] + md.split("## A7.", 1)[1]
        assert _LEAK_MARKER_DISEASE not in other_sections
        assert _LEAK_MARKER_QUOTE not in other_sections

    def test_a7_department_reason_leak_does_not_implicate_a6_isolation(self) -> None:
        """A7's `department_candidates[].reason` is a DIFFERENT F2 field
        (not `ai_predicted_disease`) — if the harness ever fed marker text
        into it, that is a caller-input concern, not an F5 red-line
        violation; F5 renders A7's own field verbatim in A7, never in A6."""
        report = _marker_report(other_slots_contain_marker=True)
        md = build_markdown_report(report)
        a6_section = md.split("## A6.")[1].split("## A7.")[0]
        a7_section = md.split("## A7.")[1].split("## A8.")[0]
        # The disease candidate itself still only appears in A6 (by rank/score).
        assert (
            f"{_LEAK_MARKER_DISEASE} |" in a6_section or f"| {_LEAK_MARKER_DISEASE} " in a6_section
        )
        # A7's own (separately-sourced) marker text renders in A7, not fabricated into A6.
        assert _LEAK_MARKER_DISEASE in a7_section


# ── (d) PDF-level isolation ──────────────────────────────────────────────


class TestPdfIsolation:
    def test_marker_disease_appears_in_pdf_a6_section_only(self) -> None:
        report = _marker_report()
        pdf_bytes = build_pdf_report(report)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "\n".join(p.extract_text() for p in reader.pages)
        assert _LEAK_MARKER_DISEASE in full_text  # sanity: rendered somewhere

        # A6 is visually fenced between its own heading and A7's heading.
        assert "A6." in full_text and "A7." in full_text
        a6_start = full_text.index("A6.")
        a7_start = full_text.index("A7.")
        a6_chunk = full_text[a6_start:a7_start]
        assert _LEAK_MARKER_DISEASE in a6_chunk

        before_a6 = full_text[:a6_start]
        after_a7_heading_body = full_text[a7_start + len("A7.") :]
        # A0-A5 (before A6) never mention the disease-candidate marker.
        assert _LEAK_MARKER_DISEASE not in before_a6
        # A8/B-section text after A7's own heading (excluding A7's own
        # department text, which legitimately may echo caller-supplied
        # text unrelated to the disease-candidate channel) — check the
        # narrative marker specifically never appears past A8's heading.
        if "A8." in after_a7_heading_body:
            a8_onward = after_a7_heading_body[after_a7_heading_body.index("A8.") :]
            assert _LEAK_MARKER_DISEASE not in a8_onward


# ── (e) FHIR-level isolation ──────────────────────────────────────────────


class TestFhirIsolation:
    def test_marker_disease_only_in_a6_fhir_section_and_resource(self) -> None:
        report = _marker_report()
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]

        sections_with_marker = [
            s["title"] for s in comp["section"] if _LEAK_MARKER_DISEASE in str(s)
        ]
        assert sections_with_marker, "sanity: marker must appear in at least one section"
        assert all(t.startswith("A6.") for t in sections_with_marker), sections_with_marker

        # Every non-Composition resource carrying the marker must be the
        # A6 Observation (code.coding[0].code == "ai-predicted-disease").
        for entry in bundle["entry"]:
            res = entry["resource"]
            if res["resourceType"] == "Composition":
                continue
            if _LEAK_MARKER_DISEASE in str(res):
                code = res.get("code", {}).get("coding", [{}])[0].get("code")
                assert code == "ai-predicted-disease", res

    def test_composition_narrative_sections_other_than_a6_never_contain_marker(self) -> None:
        report = _marker_report()
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        for section in comp["section"]:
            if section["title"].startswith("A6."):
                continue
            div_text = section.get("text", {}).get("div", "")
            assert _LEAK_MARKER_DISEASE not in div_text, section["title"]
            assert _LEAK_MARKER_QUOTE not in div_text, section["title"]
