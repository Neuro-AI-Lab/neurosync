"""Tests for the F5 FHIR R4 document Bundle builder + structural validator.

`docs/ai/f5_quick_dev_plan.md` §5.3, §7.2 check (c). Structural validity
only — NEVER an HL7 `$validate` conformance claim (D3, REV-046 MAY/MUST-NOT
wording table row 2).
"""

from __future__ import annotations

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
from src.services.f5_report import build_fhir_bundle, validate_fhir_bundle

# Every LOINC code the design doc's §5.3 mapping table marks VERIFIED.
_VERIFIED_LOINC_CODES = {
    "57143-0",  # Composition.type
    "10154-3",  # A1 chief complaint
    "10164-2",  # A2 HPI
    "84209-6",  # A3 risk section
    "10190-7",  # A4 MSE
    "44261-6",  # PHQ-9 total
    "44249-1",  # PHQ-9 panel/instrument
    "70274-6",  # GAD-7 total
    "75626-2",  # AUDIT-C total
    "51847-2",  # A8 evaluation+plan (unused this mission, narrative disabled)
}


def _report(
    *,
    all_sessions: tuple[SessionSlotSnapshot, ...] = (),
    narrative_enabled: bool = False,
    narrative_text: str | None = None,
):
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
        responses=(3, 3, 3, 3, 3, 3, 3, 3, 3),
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
            ],
            "GAD-7": [
                ScaleSeriesPoint(
                    session_index=5,
                    simulated_date="2026-10-01",
                    scale_name="GAD-7",
                    administered=True,
                    total_score=10,
                    max_score=21,
                    severity="moderate",
                )
            ],
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
        chart_filenames=ChartFilenames(scales_ctrs_sentiment="VP-TEST_x_temporal.png"),
        all_sessions=all_sessions,
        narrative_enabled=narrative_enabled,
        narrative_text=narrative_text,
    )
    return assemble_handoff_report(inp)


def _empty_report():
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


class TestBundleStructure:
    def test_bundle_is_document_type_with_composition_first(self) -> None:
        bundle = build_fhir_bundle(_report())
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "document"
        assert bundle["entry"][0]["resource"]["resourceType"] == "Composition"

    def test_validate_passes_full_report(self) -> None:
        bundle = build_fhir_bundle(_report())
        violations = validate_fhir_bundle(bundle)
        assert violations == [], violations

    def test_validate_passes_minimal_report(self) -> None:
        bundle = build_fhir_bundle(_empty_report())
        violations = validate_fhir_bundle(bundle)
        assert violations == [], violations

    def test_all_full_urls_unique(self) -> None:
        bundle = build_fhir_bundle(_report())
        full_urls = [e["fullUrl"] for e in bundle["entry"]]
        assert len(full_urls) == len(set(full_urls))
        assert all(u.startswith("urn:uuid:") for u in full_urls)


class TestReferencesResolve:
    def test_every_reference_resolves(self) -> None:
        bundle = build_fhir_bundle(_report())
        full_url_set = {e["fullUrl"] for e in bundle["entry"]}

        def walk(obj):
            if isinstance(obj, dict):
                ref = obj.get("reference")
                if isinstance(ref, str) and ref.startswith("urn:uuid:"):
                    assert ref in full_url_set, f"dangling reference {ref}"
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        walk(bundle)

    def test_validate_catches_injected_dangling_reference(self) -> None:
        bundle = build_fhir_bundle(_report())
        bundle["entry"][0]["resource"]["section"][0]["entry"] = [
            {"reference": "urn:uuid:00000000-0000-0000-0000-000000000000"}
        ]
        violations = validate_fhir_bundle(bundle)
        assert any("unresolved reference" in v for v in violations)

    def test_validate_catches_missing_required_field(self) -> None:
        bundle = build_fhir_bundle(_report())
        del bundle["entry"][0]["resource"]["title"]
        violations = validate_fhir_bundle(bundle)
        assert any("title" in v for v in violations)

    def test_validate_catches_non_document_bundle_type(self) -> None:
        bundle = build_fhir_bundle(_report())
        bundle["type"] = "collection"
        violations = validate_fhir_bundle(bundle)
        assert any("type must be 'document'" in v for v in violations)


class TestOnlyVerifiedLoincCodes:
    def test_only_verified_loinc_codes_appear(self) -> None:
        bundle = build_fhir_bundle(_report())

        def collect_loinc_codes(obj, codes: set[str]) -> None:
            if isinstance(obj, dict):
                if obj.get("system") == "http://loinc.org" and "code" in obj:
                    codes.add(obj["code"])
                for v in obj.values():
                    collect_loinc_codes(v, codes)
            elif isinstance(obj, list):
                for v in obj:
                    collect_loinc_codes(v, codes)

        found: set[str] = set()
        collect_loinc_codes(bundle, found)
        assert found, "sanity: at least one LOINC code must appear"
        assert found.issubset(_VERIFIED_LOINC_CODES), found - _VERIFIED_LOINC_CODES

    def test_a6_uses_local_code_system_not_loinc(self) -> None:
        """A6 has no LOINC/SNOMED code per the design doc's own §5.3
        table (N/A/UNVERIFIED row) — must use the disclosed local code
        system, never an invented LOINC code."""
        bundle = build_fhir_bundle(_report())
        comp = bundle["entry"][0]["resource"]
        a6_section = next(s for s in comp["section"] if s["title"].startswith("A6."))
        assert a6_section["code"]["coding"][0]["system"] == "urn:neurosync:f5-local-codes"


class TestQuestionnaireResponseItemCounts:
    def test_item_count_matches_responses(self) -> None:
        report = _report()
        n_responses = len(report.a5_questionnaires.responses)
        assert n_responses == 9  # PHQ-9

        bundle = build_fhir_bundle(report)
        qr = next(
            e["resource"]
            for e in bundle["entry"]
            if e["resource"]["resourceType"] == "QuestionnaireResponse"
        )
        assert len(qr["item"]) == n_responses
        for i, item in enumerate(qr["item"]):
            assert item["answer"][0]["valueInteger"] == report.a5_questionnaires.responses[i]

    def test_no_questionnaire_response_when_a5_absent(self) -> None:
        bundle = build_fhir_bundle(_empty_report())
        qrs = [
            e for e in bundle["entry"] if e["resource"]["resourceType"] == "QuestionnaireResponse"
        ]
        assert qrs == []


class TestDisclaimerAndNonDiagnostic:
    def test_disclaimer_section_present_verbatim(self) -> None:
        report = _report()
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        disclaimer_section = next(
            s for s in comp["section"] if s["code"].get("text") == "disclaimer"
        )
        assert report.disclaimer in disclaimer_section["text"]["div"]

    def test_a6_note_states_not_a_diagnosis(self) -> None:
        bundle = build_fhir_bundle(_report())
        obs = next(
            e["resource"]
            for e in bundle["entry"]
            if e["resource"]["resourceType"] == "Observation"
            and e["resource"]["code"]["coding"][0].get("code") == "ai-predicted-disease"
        )
        notes_text = " ".join(n["text"] for n in obs["note"])
        assert "NOT A DIAGNOSIS" in notes_text
        assert "PROBABILITY" in notes_text.upper()

    def test_a3_risk_assessment_note_carries_non_validated_caveat(self) -> None:
        """EXP-024 check 5c FAIL regression, FHIR format: the staleness
        pointer embeds a scored PHQ-9 number (session 9, 27/27) inside
        `RiskAssessment.note` — that note must also carry the
        non-validated-administration caveat, mirroring A5's QuestionnaireResponse/
        Observation notes."""
        report = _report()
        assert report.a3_risk_safety.staleness_pointer.total_score is not None  # sanity
        bundle = build_fhir_bundle(report)
        risk_assessment = next(
            e["resource"]
            for e in bundle["entry"]
            if e["resource"]["resourceType"] == "RiskAssessment"
        )
        notes_text = " ".join(n["text"] for n in risk_assessment["note"])
        assert "검증된 임상 설문 시행이 아닙니다" in notes_text

    def test_b5_no_images_in_bundle(self) -> None:
        """Design doc §5.3 B5 row: v0 bundle contains NO images (D3)."""
        bundle = build_fhir_bundle(_report())
        assert not any(e["resource"].get("resourceType") == "Media" for e in bundle["entry"])

    def test_no_fhir_conformance_claim_in_rendered_output(self) -> None:
        """REV-046 MAY/MUST-NOT wording table row 2: the RENDERED bundle
        (never the module's own docstring, which legitimately discusses
        this rule in negated prose) must never claim 'FHIR-conformant',
        'validated against the FHIR spec', or `$validate`-passed."""
        import json

        bundle = build_fhir_bundle(_report())
        rendered = json.dumps(bundle, ensure_ascii=False).lower()
        assert "fhir-conformant" not in rendered
        assert "validated against the fhir spec" not in rendered
        assert "$validate" not in rendered


# ── A8 FHIR-omission note (ADR-038 Decision 2d, CVR-024 Rec 6) ──────────


class TestA8OmissionNote:
    def test_disclaimer_section_carries_a8_omission_note_when_narrative_disabled(self) -> None:
        from src.schemas.handoff_report import A8_FHIR_OMISSION_NOTE_KO

        report = _report()
        assert report.a8_narrative.narrative_enabled is False  # sanity
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        disclaimer_section = next(
            s for s in comp["section"] if s["code"].get("text") == "disclaimer"
        )
        assert A8_FHIR_OMISSION_NOTE_KO in disclaimer_section["text"]["div"]

    def test_no_a8_titled_section_exists(self) -> None:
        """REV-047 Criterion 6a precedent (PASS-via-stronger-disposition)
        stands unchanged -- the omission note is a ONE-LINE addendum to the
        disclaimer section, not a new checkable A8 placeholder section."""
        bundle = build_fhir_bundle(_report())
        comp = bundle["entry"][0]["resource"]
        assert not any(s["title"].startswith("A8") for s in comp["section"])

    def test_bundle_still_validates_structurally(self) -> None:
        bundle = build_fhir_bundle(_report())
        assert validate_fhir_bundle(bundle) == []


# ── A6 reason_summary surfacing, FHIR (ADR-038 Decision 2b) ──────────────


class TestA6ReasonSummaryFhir:
    def _report_with_apd(self, apd: AIPredictedDiseaseOutput):
        session = SessionSnapshot(
            session_id="f1_VP-TEST",
            persona_id="VP-TEST",
            persona_name="김테스트",
            session_index=11,
            simulated_date="2027-01-12",
            model="solar-pro3-260323",
            final_slots={"chief_complaint": "x"},
            session_ctrs=4,
            crisis_triggered=False,
            crisis_turn=None,
            risk_floor=None,
            probe_event_count=0,
        )
        inp = HandoffReportInput(
            vp_id="VP-TEST",
            session=session,
            current_session_f3=None,
            all_f3_administrations=(),
            domain_inference=DomainInferenceSnapshot(ai_predicted_disease=apd),
            longitudinal=LongitudinalAnalysisOutput(vp_id="VP-TEST", n_sessions=1),
        )
        return assemble_handoff_report(inp)

    def test_a6_section_text_includes_reason_summary_when_unpopulated(self) -> None:
        apd = AIPredictedDiseaseOutput(
            candidates=[],
            mode="experimental_unpopulated",
            reason_summary="no RAG chunks retrieved this run",
        )
        report = self._report_with_apd(apd)
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        a6_section = next(s for s in comp["section"] if s["title"].startswith("A6"))
        assert "no RAG chunks retrieved this run" in a6_section["text"]["div"]

    def test_a6_section_text_omits_reason_summary_for_rag_live_empty(self) -> None:
        apd = AIPredictedDiseaseOutput(
            candidates=[], mode="rag_live", reason_summary="should not appear"
        )
        report = self._report_with_apd(apd)
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        a6_section = next(s for s in comp["section"] if s["title"].startswith("A6"))
        assert "should not appear" not in a6_section["text"]["div"]


# ── A7 validation-drop disclosure, FHIR (ADR-038 Decision 2a) ────────────


class TestA7DisclosureFhir:
    def _report_no_departments(self, *, validation_errors_present: bool):
        session = SessionSnapshot(
            session_id="f1_VP-TEST",
            persona_id="VP-TEST",
            persona_name="김테스트",
            session_index=11,
            simulated_date="2027-01-12",
            model="solar-pro3-260323",
            final_slots={"chief_complaint": "x"},
            session_ctrs=4,
            crisis_triggered=False,
            crisis_turn=None,
            risk_floor=None,
            probe_event_count=0,
        )
        inp = HandoffReportInput(
            vp_id="VP-TEST",
            session=session,
            current_session_f3=None,
            all_f3_administrations=(),
            domain_inference=DomainInferenceSnapshot(
                ai_predicted_disease=AIPredictedDiseaseOutput(
                    candidates=[], mode="experimental_unpopulated"
                ),
                department_candidates=(),
                validation_errors_present=validation_errors_present,
            ),
            longitudinal=LongitudinalAnalysisOutput(vp_id="VP-TEST", n_sessions=1),
        )
        return assemble_handoff_report(inp)

    def test_a7_section_text_shows_validation_dropped_wording(self) -> None:
        report = self._report_no_departments(validation_errors_present=True)
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        a7_section = next(s for s in comp["section"] if s["title"].startswith("A7"))
        assert "VAL-016" in a7_section["text"]["div"]

    def test_a7_section_text_shows_model_judged_wording(self) -> None:
        report = self._report_no_departments(validation_errors_present=False)
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        a7_section = next(s for s in comp["section"] if s["title"].startswith("A7"))
        assert "VAL-016" not in a7_section["text"]["div"]
        assert "모델 판정" in a7_section["text"]["div"]


# ── Exact-ceiling caveat co-location, FHIR (ADR-038 Decision 2c) ─────────


class TestCeilingCaveatFhir:
    def test_risk_assessment_note_carries_ceiling_caveat_for_ceiling_score(self) -> None:
        """`_report()`'s staleness-pointer administration is PHQ-9 27/27
        (scale ceiling) -- the RiskAssessment note (already carrying the
        staleness pointer text) must also carry the ISS-F2V-028 caveat."""
        report = _report()
        assert report.a3_risk_safety.staleness_pointer.ceiling_caveat is not None  # sanity
        bundle = build_fhir_bundle(report)
        risk_assessment = next(
            e["resource"]
            for e in bundle["entry"]
            if e["resource"]["resourceType"] == "RiskAssessment"
        )
        notes_text = " ".join(n["text"] for n in risk_assessment["note"])
        assert "ISS-F2V-028" in notes_text

    def test_a5_total_observation_note_carries_ceiling_caveat(self) -> None:
        report = _report()
        assert report.a5_questionnaires.ceiling_caveat is not None  # sanity
        bundle = build_fhir_bundle(report)
        a5_obs = next(
            e["resource"]
            for e in bundle["entry"]
            if e["resource"]["resourceType"] == "Observation"
            and e["resource"]["code"].get("text", "").startswith("PHQ-9")
        )
        notes_text = " ".join(n["text"] for n in a5_obs["note"])
        assert "ISS-F2V-028" in notes_text


# ── All-session slot overview, FHIR (Task 1) ─────────────────────────────

_FHIR_SLOT_SESSIONS = (
    SessionSlotSnapshot(9, "2026-11-12", {"chief_complaint": "이전 세션 주호소"}),
    SessionSlotSnapshot(
        11, "2027-01-12", {"chief_complaint": "잠을 잘 못 자는 것이 가장 신경 쓰임"}
    ),
)


class TestSlotOverviewFhir:
    def test_slot_overview_section_present_with_local_code(self) -> None:
        bundle = build_fhir_bundle(_report(all_sessions=_FHIR_SLOT_SESSIONS))
        comp = bundle["entry"][0]["resource"]
        section = next(s for s in comp["section"] if s["title"].startswith("A1-A2 확장"))
        assert section["code"]["coding"][0]["system"] == "urn:neurosync:f5-local-codes"
        assert "잠을 잘 못 자는 것이 가장 신경 쓰임" in section["text"]["div"]
        assert "미수집" in section["text"]["div"]

    def test_bundle_still_validates_structurally_with_slot_overview(self) -> None:
        bundle = build_fhir_bundle(_report(all_sessions=_FHIR_SLOT_SESSIONS))
        assert validate_fhir_bundle(bundle) == []

    def test_slot_overview_never_uses_loinc(self) -> None:
        bundle = build_fhir_bundle(_report(all_sessions=_FHIR_SLOT_SESSIONS))

        def collect_loinc(obj, codes):
            if isinstance(obj, dict):
                if obj.get("system") == "http://loinc.org" and "code" in obj:
                    codes.add(obj["code"])
                for v in obj.values():
                    collect_loinc(v, codes)
            elif isinstance(obj, list):
                for v in obj:
                    collect_loinc(v, codes)

        comp = bundle["entry"][0]["resource"]
        section = next(s for s in comp["section"] if s["title"].startswith("A1-A2 확장"))
        codes: set[str] = set()
        collect_loinc(section, codes)
        assert codes == set()


# ── A8 opt-in narrative, FHIR (Task 2, handoff_generator v3) ────────────


class TestNarrativeOptInFhir:
    def test_enabled_with_text_adds_a8_section_and_drops_omission_note(self) -> None:
        from src.schemas.handoff_report import A8_FHIR_OMISSION_NOTE_KO

        report = _report(narrative_enabled=True, narrative_text="환자는 수면 문제를 자가보고함.")
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        a8_section = next(s for s in comp["section"] if s["title"].startswith("A8"))
        assert "환자는 수면 문제를 자가보고함." in a8_section["text"]["div"]
        assert a8_section["code"]["coding"][0]["code"] == "51847-2"

        disclaimer_section = next(
            s for s in comp["section"] if s["code"].get("text") == "disclaimer"
        )
        assert A8_FHIR_OMISSION_NOTE_KO not in disclaimer_section["text"]["div"]

    def test_rejected_narrative_keeps_omission_note_and_no_a8_section(self) -> None:
        """A caller-supplied narrative that leaks an A6 disease name is
        REFUSED by `f5.py::_build_a8` — the FHIR bundle must treat that
        exactly like the disabled-by-default case (no A8 section, omission
        note present), never render the refused text."""
        from src.schemas.handoff_report import A8_FHIR_OMISSION_NOTE_KO

        report = _report(
            narrative_enabled=True,
            narrative_text="환자는 계절성 정동장애 소견이 의심됨.",
        )
        assert report.a8_narrative.narrative_enabled is False  # sanity: rejected
        bundle = build_fhir_bundle(report)
        comp = bundle["entry"][0]["resource"]
        assert not any(s["title"].startswith("A8") for s in comp["section"])
        disclaimer_section = next(
            s for s in comp["section"] if s["code"].get("text") == "disclaimer"
        )
        assert A8_FHIR_OMISSION_NOTE_KO in disclaimer_section["text"]["div"]
        assert "계절성 정동장애" not in disclaimer_section["text"]["div"]

    def test_bundle_still_validates_structurally_with_a8_enabled(self) -> None:
        report = _report(narrative_enabled=True, narrative_text="환자는 수면 문제를 자가보고함.")
        bundle = build_fhir_bundle(report)
        assert validate_fhir_bundle(bundle) == []
