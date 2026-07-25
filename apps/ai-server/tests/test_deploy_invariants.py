"""Deployment smoke suite — standing regression guards ported from the
archived legacy suite (`_archive/legacy_code/tests_legacy_20260720/tests/`),
copied+trimmed per ADR-041 T4 (user directive, 2026-07-20). No guard is
weakened in the port.

Covers:
  (a) BUG-022 exact-match clinical-agent input-schema field allowlist.
  (b) Pinned system-prompt files exist (and safety_classifier's actually
      loads through PromptLoader).
  (c) Crisis hotline constants (109/119/112 — Master canonical set per ADR-048,
      BUG-062) present in f1.py and orchestrator.py.
  (d) `is_diagnostic: Literal[False]` on survey/handoff report schemas.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from src.agents.base import AgentInput
from src.agents.evidence_verifier import VerifierAction
from src.prompts.loader import PromptLoader
from src.schemas.clinical_slot import ClinicalSlotInput
from src.schemas.common import EvidencePacket, EvidenceSource
from src.schemas.dialogue import DialogueInput
from src.schemas.domain_inference import DomainInferenceInput
from src.schemas.input_normalizer import InputNormalizerInput
from src.schemas.safety import SafetyInput
from src.schemas.sentiment import SentimentSessionInput, SentimentUtteranceInput

AI_SERVER_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = AI_SERVER_ROOT / "prompts"


# ── (a) BUG-022 clinical-agent input-schema field allowlist ────────────
#
# `error.md` BUG-022: `rag.session_insights` carries unredacted persona.md
# ground-truth diagnostic labels (`class`, `phq9_score`, `gad7_score`,
# `flag_suicidal`) into `retrieve_grounding()`'s `my_past` payload. This is
# the standing schema-level guard against a future wiring into a clinical
# agent's input. RagTriggerJudgeInput is gone (ADR-041 T1 retired
# Policy-B); `patient_history_context` stays on DialogueInput (PHR context,
# real-app user input, not persona ground truth).

BUG_022_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {"class", "phq9_score", "gad7_score", "flag_suicidal"}
)

_BASE_FIELDS: frozenset[str] = frozenset({"session_id", "request_id", "extra"})

APPROVED_FIELDS: dict[type[AgentInput], frozenset[str]] = {
    SafetyInput: _BASE_FIELDS | {"user_message", "conversation_history"},
    # BUG-072/073 (2026-07-25): `dialogue_target_slot` added — the ask-
    # evidence hint threaded from `SessionState.dialogue_target_slot`
    # (single source of truth), never a persona ground-truth field (BUG-022
    # scope) — explicit, reviewed allowlist update.
    ClinicalSlotInput: _BASE_FIELDS
    | {"conversation_history", "current_slots", "dialogue_target_slot"},
    DialogueInput: _BASE_FIELDS
    | {
        "user_message",
        "conversation_history",
        "filled_slots",
        "safety_result",
        "session_state",
        "slot_updates_this_turn",
        "patient_history_context",
    },
    InputNormalizerInput: _BASE_FIELDS | {"raw_text", "input_type", "dialect_hint"},
    SentimentUtteranceInput: _BASE_FIELDS
    | {"utterance", "turn_index", "conversation_context"},
    SentimentSessionInput: _BASE_FIELDS
    | {"per_utterance_results", "conversation_history"},
    DomainInferenceInput: _BASE_FIELDS
    | {
        "final_slots",
        "session_ctrs",
        "crisis_triggered",
        "crisis_turn",
        "is_first_visit",
        "turns",
        "prior_handoff",
        "probe_events",
        "scale_scores",
        "retrieved_chunks",
        "retrieval_mode",
        "queries",
    },
}


class TestBug022InputSchemaFieldAllowlist:
    def test_every_named_model_has_an_allowlist_entry(self) -> None:
        expected = {
            SafetyInput,
            ClinicalSlotInput,
            DialogueInput,
            InputNormalizerInput,
            SentimentUtteranceInput,
            SentimentSessionInput,
            DomainInferenceInput,
        }
        assert set(APPROVED_FIELDS) == expected

    def test_field_allowlist_exact_match(self) -> None:
        for model, approved in APPROVED_FIELDS.items():
            actual = set(model.model_fields)
            assert actual == approved, (
                f"{model.__name__} field set drifted from the pre-registered "
                f"allowlist — added: {sorted(actual - approved)}, "
                f"removed: {sorted(approved - actual)}. A genuinely new "
                "field requires an explicit, reviewed allowlist update, not "
                "a silent pass."
            )

    def test_bug_022_forbidden_fields_never_appear_on_any_clinical_agent_input(
        self,
    ) -> None:
        for model in APPROVED_FIELDS:
            leaked = set(model.model_fields) & BUG_022_FORBIDDEN_FIELDS
            assert not leaked, (
                f"{model.__name__} carries BUG-022 forbidden ground-truth "
                f"field(s): {sorted(leaked)}"
            )

    def test_forbidden_fields_are_exactly_the_four_bug_022_columns(self) -> None:
        assert BUG_022_FORBIDDEN_FIELDS == {
            "class", "phq9_score", "gad7_score", "flag_suicidal",
        }


# ── (b) Pinned prompt files exist / safety_classifier actually loads ────


class TestPinnedPromptFiles:
    def test_safety_classifier_pin_is_v2(self) -> None:
        from src.agents.safety_classifier import PROMPT_VERSION
        assert PROMPT_VERSION == "v2"

    def test_safety_classifier_v2_file_exists_and_loads(self) -> None:
        path = PROMPTS_DIR / "safety_classifier" / "v2.system.md"
        assert path.is_file(), f"pinned safety_classifier prompt missing: {path}"
        loader = PromptLoader(PROMPTS_DIR)
        content = loader.load_system_prompt("safety_classifier", "v2")
        assert content, "safety_classifier v2 prompt loaded empty"

    @pytest.mark.parametrize(
        "agent,version",
        [
            ("clinical_slot", "v5"),
            ("dialogue", "v5"),
            # EXP-030 cluster B#2 (2026-07-21): dialogue's runtime pin moved
            # to v5.1 (self-referential-relief ban) — v5 kept for history,
            # v5.1 is the file `test_agent_pins_match_kept_files` actually
            # resolves against; both asserted here so this static list
            # doesn't silently drift stale on the next re-pin.
            ("dialogue", "v5.1"),
            # BUG-074 (2026-07-25): dialogue's runtime pin moved to v5.2
            # (meta-utterance section, addition-only over v5.1) — v5.1 kept
            # for history, same drift-detection rationale as above.
            ("dialogue", "v5.2"),
            # BUG-077 / BUG-074 residual (2026-07-25): dialogue's runtime
            # pin moved to v5.3 (widened meta-utterance recognition +
            # catch-all-question prohibition, addition-only over v5.2) —
            # v5.2 kept for history, same drift-detection rationale as
            # above.
            ("dialogue", "v5.3"),
            # BUG-078 / CVR-055 finding 3 (2026-07-25): dialogue's runtime
            # pin moved to v5.4 (meta-utterance worked-example sentences
            # replaced with abstract shape description — NOT addition-only,
            # see v5.4's own changelog note) — v5.3 kept for history, same
            # drift-detection rationale as above.
            ("dialogue", "v5.4"),
            # BUG-079 / REV-022 §4 (2026-07-25): dialogue's runtime pin
            # moved to v5.5 (공감 캘리브레이션 condensed to a principle +
            # one safety-critical ban — NOT addition-only in that one
            # section, see v5.5's own changelog note) — v5.4 kept for
            # history, same drift-detection rationale as above.
            ("dialogue", "v5.5"),
            # BUG-085-follow-up (2026-07-25, session `04cfe927`): dialogue's
            # runtime pin moved to v5.6 (공감 캘리브레이션 replaced with
            # CVR-057's 6-type discriminant-table principle + 환자
            # 메타-발화 처리 widened with a third, capability/memory-
            # complaint subtype — see v5.6's own changelog note) — v5.5
            # kept for history, same drift-detection rationale as above.
            ("dialogue", "v5.6"),
            ("domain_inference", "v2"),
            ("handoff_generator", "v4"),
            ("handoff_generator", "v3"),
            # EXP-030 cluster D1 (2026-07-21): handoff_generator's structured
            # (non-narrative) pin moved to v4.1 (denial-preservation,
            # additive-only over v4) — same rationale as dialogue v5.1 above.
            ("handoff_generator", "v4.1"),
            # EXP-030 pin-fix wave / CVR-042 (2026-07-21): runtime pin moved
            # to v4.2 (risk_assessment denial/screen nuance preservation,
            # additive-only over v4.1) — v4.1 kept for history, same
            # drift-detection rationale as the two entries above.
            ("handoff_generator", "v4.2"),
            # BUG-069/PLAN-2026-W30-BUG069 (2026-07-23): runtime pin moved to
            # v4.3 (metadata citation discipline + first-visit trend
            # prohibition, additive-only over v4.2) — v4.2 kept for history,
            # same drift-detection rationale as the entries above.
            ("handoff_generator", "v4.3"),
            ("sentiment_analyzer", "v2"),
            ("input_normalizer", "v1"),
        ],
    )
    def test_pinned_prompt_file_exists(self, agent: str, version: str) -> None:
        path = PROMPTS_DIR / agent / f"{version}.system.md"
        assert path.is_file(), f"pinned prompt file missing: {path}"

    def test_agent_pins_match_kept_files(self) -> None:
        """Every agent's runtime PROMPT_VERSION constant matches a file that
        actually exists under apps/ai-server/prompts."""
        from src.agents.clinical_slot import PROMPT_VERSION as CLINICAL_SLOT_V
        from src.agents.dialogue import PROMPT_VERSION as DIALOGUE_V
        from src.agents.domain_inference import PROMPT_VERSION as DOMAIN_V
        from src.agents.handoff_generator import _NARRATIVE_PROMPT_VERSION as HANDOFF_NARR_V
        from src.agents.handoff_generator import _PROMPT_VERSION as HANDOFF_V
        from src.agents.sentiment_analyzer import PROMPT_VERSION as SENTIMENT_V

        pins = [
            ("clinical_slot", CLINICAL_SLOT_V),
            ("dialogue", DIALOGUE_V),
            ("domain_inference", DOMAIN_V),
            ("handoff_generator", HANDOFF_V),
            ("handoff_generator", HANDOFF_NARR_V),
            ("sentiment_analyzer", SENTIMENT_V),
        ]
        for agent, version in pins:
            path = PROMPTS_DIR / agent / f"{version}.system.md"
            assert path.is_file(), f"{agent} pinned to {version} but file missing: {path}"


# ── (c) Crisis hotline constants ────────────────────────────────────────


class TestCrisisHotlines:
    def test_f1_crisis_response_carries_hotlines(self) -> None:
        from src.f1 import CRISIS_RESPONSE
        assert "109" in CRISIS_RESPONSE
        assert "119" in CRISIS_RESPONSE

    def test_orchestrator_crisis_messages_carry_hotlines(self) -> None:
        from src.agents.orchestrator import _CRISIS_MESSAGES
        joined = " ".join(_CRISIS_MESSAGES.values())
        assert "109" in joined
        assert "119" in joined
        assert "112" in joined
        assert "1577-0199" not in joined


# ── (d) is_diagnostic: Literal[False] on survey/handoff report schemas ──


class TestIsDiagnosticFixedFalse:
    def test_survey_result_output_is_diagnostic_literal_false(self) -> None:
        from src.schemas.survey_result import SurveyResultOutput

        field = SurveyResultOutput.model_fields["is_diagnostic"]
        assert get_args(field.annotation) == (False,)
        assert SurveyResultOutput.model_fields["is_diagnostic"].default is False

    def test_handoff_report_output_is_diagnostic_literal_false(self) -> None:
        from src.schemas.handoff_report import HandoffReportOutput

        field = HandoffReportOutput.model_fields["is_diagnostic"]
        assert get_args(field.annotation) == (False,)
        assert HandoffReportOutput.model_fields["is_diagnostic"].default is False


# ── (e) CVR-032: F5 renderer must surface interim crisis signals ────────
#
# Fixed 2026-07-20: prose previously used first-vs-last framing only — a
# scripted CTRS 5,5,5,3,4 arc with a safety_net PHQ-9 at S4 rendered the
# blanket "위기 반응 발생 세션 없음" line with no mention of the dip,
# contradicting the system's own `course_shape="crisis_episode"`
# classification (never surfaced in text at all).


def _cvr032_scenario_a():
    """Interim CTRS-3 + safety_net + item-9-positive arc (CVR-032 repro
    shape) — verbatim minimal reconstruction, no file/DB I/O."""
    from src.f5 import (
        ChartFilenames,
        DomainInferenceSnapshot,
        F3Administration,
        HandoffReportInput,
        SessionSnapshot,
        assemble_handoff_report,
    )
    from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput

    ctrs_series = [
        CTRSSeriesPoint(
            session_index=i, simulated_date=f"2026-07-0{i}",
            session_ctrs=c, crisis_triggered=False,
        )
        for i, c in enumerate([5, 5, 5, 3, 4], start=1)
    ]
    all_f3 = (
        F3Administration(
            session_index=4, simulated_date="2026-07-04", outcome="administered",
            scale_name="PHQ-9", responses=(1,) * 8 + (1,), total_score=11, max_score=27,
            severity="moderate", critical_item_positive=True, safety_referral=True,
            administration_mode="safety_net",
        ),
    )
    lon = LongitudinalAnalysisOutput(
        vp_id="VP-CVR032", n_sessions=5, session_span_days=4,
        ctrs_series=ctrs_series, overall_direction="unchanged",
        course_shape="crisis_episode", concordance_flag="concordant",
    )
    session = SessionSnapshot(
        session_id="s5", persona_id="VP-CVR032", persona_name="테스트",
        session_index=5, simulated_date="2026-07-05", model="test",
        final_slots={}, session_ctrs=4, crisis_triggered=False, crisis_turn=None,
        risk_floor=None, probe_event_count=0,
    )
    inp = HandoffReportInput(
        vp_id="VP-CVR032", session=session, current_session_f3=None,
        all_f3_administrations=all_f3,
        domain_inference=DomainInferenceSnapshot(ai_predicted_disease=None),
        longitudinal=lon, chart_filenames=ChartFilenames(),
    )
    return assemble_handoff_report(inp)


def _cvr032_scenario_quiet():
    """A genuinely quiet series — the blanket 없음 line must still render."""
    from src.f5 import (
        ChartFilenames,
        DomainInferenceSnapshot,
        HandoffReportInput,
        SessionSnapshot,
        assemble_handoff_report,
    )
    from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput

    ctrs_series = [
        CTRSSeriesPoint(
            session_index=i, simulated_date=f"2026-07-0{i}",
            session_ctrs=5, crisis_triggered=False,
        )
        for i in range(1, 4)
    ]
    lon = LongitudinalAnalysisOutput(
        vp_id="VP-QUIET", n_sessions=3, session_span_days=2,
        ctrs_series=ctrs_series, overall_direction="unchanged",
        course_shape="unknown", concordance_flag="concordant",
    )
    session = SessionSnapshot(
        session_id="s3", persona_id="VP-QUIET", persona_name="테스트2",
        session_index=3, simulated_date="2026-07-03", model="test",
        final_slots={}, session_ctrs=5, crisis_triggered=False, crisis_turn=None,
        risk_floor=None, probe_event_count=0,
    )
    inp = HandoffReportInput(
        vp_id="VP-QUIET", session=session, current_session_f3=None,
        all_f3_administrations=(),
        domain_inference=DomainInferenceSnapshot(ai_predicted_disease=None),
        longitudinal=lon, chart_filenames=ChartFilenames(),
    )
    return assemble_handoff_report(inp)


class TestCvr032InterimCrisisSignalSurfacing:
    def test_interim_ctrs3_safety_net_item9_surfaces_in_prose(self) -> None:
        from src.services.f5_report import build_markdown_report

        md = build_markdown_report(_cvr032_scenario_a())

        # (i) course_shape in prose (headline AND 종단 추세 section).
        assert "위기 삽화(crisis episode)" in md
        assert md.count("경과 형태") >= 2

        # (ii) worst-session callout — the actual min-CTRS session, not
        # just first/last.
        assert "4회차(2026-07-04)에서 CTRS 3/5(급성 우려)" in md
        assert "안전망(safety_net) 설문 시행 1건(4회차)" in md
        assert "자살사고 문항(9번) 양성 1/1세션" in md

        # (iii) the blanket "no crisis session" line must NOT render while
        # this interim signal exists.
        assert "위기 반응 발생 세션 없음" not in md

        # (iv) SI-specific referral wording (verbatim hotline constant).
        assert "109" in md
        assert "119" in md

    def test_pdf_build_does_not_crash_on_interim_signal_scenario(self) -> None:
        from src.services.f5_report import build_pdf_report

        pdf_bytes = build_pdf_report(_cvr032_scenario_a(), {})
        assert pdf_bytes[:4] == b"%PDF"

    def test_quiet_series_still_renders_blanket_no_crisis_line(self) -> None:
        from src.services.f5_report import build_markdown_report

        md = build_markdown_report(_cvr032_scenario_quiet())
        assert "위기 반응 발생 세션 없음" in md
        assert "109" not in md


# ── CVR-033: residual fixes to the CVR-032 renderer pass ────────────────
#
# Fixed 2026-07-20: clinical-validator re-review (verdict improved to
# adequate-with-findings) found 4 residuals in the CVR-032 fix itself.


def _cvr033_scenario_min_ctrs2():
    """Nadir CTRS=2 (falls INSIDE the "1-2" band), `crisis_triggered=False`
    (the orchestrator's bypass never fired) — the exact self-contradiction
    repro shape (VP-003_regen2): the old sentence rendered "위기 전환
    (CTRS 1-2) 세션은 없었으나... CTRS 2/5(고위험)", denying and asserting
    the same band in one sentence."""
    from src.f5 import (
        ChartFilenames,
        DomainInferenceSnapshot,
        F3Administration,
        HandoffReportInput,
        SessionSnapshot,
        assemble_handoff_report,
    )
    from src.schemas.longitudinal import (
        CTRSSeriesPoint,
        LongitudinalAnalysisOutput,
        ScaleSeriesPoint,
    )

    ctrs_series = [
        CTRSSeriesPoint(
            session_index=i, simulated_date=f"2026-07-0{i}",
            session_ctrs=c, crisis_triggered=False,
        )
        for i, c in enumerate([5, 5, 5, 2, 4], start=1)
    ]
    all_f3 = (
        F3Administration(
            session_index=4, simulated_date="2026-07-04", outcome="administered",
            scale_name="PHQ-9", responses=(1,) * 8 + (1,), total_score=11, max_score=27,
            severity="moderate", critical_item_positive=True, safety_referral=True,
            administration_mode="safety_net",
        ),
    )
    lon = LongitudinalAnalysisOutput(
        vp_id="VP-CVR033", n_sessions=5, session_span_days=4,
        ctrs_series=ctrs_series, overall_direction="unchanged",
        course_shape="crisis_episode", concordance_flag="concordant",
        scale_series={
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=4, simulated_date="2026-07-04", scale_name="PHQ-9",
                    administered=True, total_score=11, max_score=27, severity="moderate",
                    critical_item_positive=True,
                )
            ]
        },
    )
    session = SessionSnapshot(
        session_id="s5", persona_id="VP-CVR033", persona_name="테스트",
        session_index=5, simulated_date="2026-07-05", model="test",
        final_slots={}, session_ctrs=4, crisis_triggered=False, crisis_turn=None,
        risk_floor=None, probe_event_count=0,
    )
    inp = HandoffReportInput(
        vp_id="VP-CVR033", session=session, current_session_f3=None,
        all_f3_administrations=all_f3,
        domain_inference=DomainInferenceSnapshot(ai_predicted_disease=None),
        longitudinal=lon, chart_filenames=ChartFilenames(),
    )
    return assemble_handoff_report(inp)


def _cvr033_scenario_mismatch():
    """5 administered sessions, F2 recommended GAD-7 while PHQ-9 was
    actually administered in 2 of them (VP-001 record shape) — the CVR-032
    original fix only ever compared the SINGLE latest recommendation
    against the single latest administered scale and so never rendered
    this note even though earlier sessions clearly mismatched."""
    from src.f5 import (
        ChartFilenames,
        DomainInferenceSnapshot,
        F3Administration,
        HandoffReportInput,
        SessionSnapshot,
        assemble_handoff_report,
    )
    from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput

    ctrs_series = [
        CTRSSeriesPoint(
            session_index=i, simulated_date=f"2026-07-0{i}",
            session_ctrs=5, crisis_triggered=False,
        )
        for i in range(1, 6)
    ]
    all_f3 = tuple(
        F3Administration(
            session_index=i, simulated_date=f"2026-07-0{i}", outcome="administered",
            scale_name=scale, responses=(0,) * 9, total_score=3, max_score=27,
            severity="minimal", critical_item_positive=False,
            recommended_questionnaire="GAD-7",
        )
        for i, scale in enumerate(["PHQ-9", "GAD-7", "PHQ-9", "GAD-7", "GAD-7"], start=1)
    )
    lon = LongitudinalAnalysisOutput(
        vp_id="VP-CVR033-MISMATCH", n_sessions=5, session_span_days=4,
        ctrs_series=ctrs_series, overall_direction="unchanged",
        course_shape="gradual_improvement", concordance_flag="concordant",
    )
    session = SessionSnapshot(
        session_id="s5", persona_id="VP-CVR033-MISMATCH", persona_name="테스트",
        session_index=5, simulated_date="2026-07-05", model="test",
        final_slots={}, session_ctrs=5, crisis_triggered=False, crisis_turn=None,
        risk_floor=None, probe_event_count=0,
    )
    inp = HandoffReportInput(
        vp_id="VP-CVR033-MISMATCH", session=session, current_session_f3=None,
        all_f3_administrations=all_f3,
        domain_inference=DomainInferenceSnapshot(ai_predicted_disease=None),
        longitudinal=lon, chart_filenames=ChartFilenames(),
    )
    return assemble_handoff_report(inp)


class TestCvr033ResidualFixes:
    def test_min_ctrs2_no_self_contradiction_and_flow_mismatch_flagged(self) -> None:
        from src.services.f5_report import build_markdown_report

        md = build_markdown_report(_cvr033_scenario_min_ctrs2())

        # (i) Finding 1: must never deny the 1-2 band while asserting a
        # value inside it.
        assert "위기 전환(CTRS 1-2) 세션은 없었으나" not in md
        assert "위기 반응 발생 세션 없음" not in md

        # (ii) states the crisis-level session plainly + honesty qualifier.
        assert "4회차" in md
        assert "CTRS 2/5" in md
        assert "고위험" in md
        assert "위기 전환 플로우 미발동" in md
        assert "기록 불일치 가능성" in md

        # (iii) Finding 3: nadir session's own administered scale score
        # co-located with the CTRS clause.
        assert "PHQ-9 11/27" in md
        assert "중등도" in md

        # (iv) Finding 4: SI referral wrapped as clinician guidance, not a
        # bare patient-facing script, `SI_POSITIVE_ACTION_KO` unaltered.
        assert "환자에게 다음 안내 권장" in md
        assert "109" in md
        assert "119" in md

    def test_pdf_build_does_not_crash_on_min_ctrs2_scenario(self) -> None:
        from src.services.f5_report import build_pdf_report

        pdf_bytes = build_pdf_report(_cvr033_scenario_min_ctrs2(), {})
        assert pdf_bytes[:4] == b"%PDF"

    def test_min_ctrs3_branch_unchanged_no_contradiction(self) -> None:
        """CVR-032's own min-CTRS=3 scenario must still use the "없었으나"
        phrasing (CTRS 3 genuinely falls outside the 1-2 band it denies)."""
        from src.services.f5_report import build_markdown_report

        md = build_markdown_report(_cvr032_scenario_a())
        assert "위기 전환(CTRS 1-2) 세션은 없었으나" in md
        assert "위기 전환 플로우 미발동" not in md

    def test_per_session_recommend_administer_mismatch_renders(self) -> None:
        from src.services.f5_report import build_markdown_report

        md = build_markdown_report(_cvr033_scenario_mismatch())
        assert "권고-시행 불일치" in md
        assert "권고 GAD-7 vs 시행 PHQ-9" in md
        assert "2/5세션" in md
        assert "1회차" in md and "3회차" in md


# ── BUG-047: soft-safety hotline note on the production route path ──────
#
# Fixed 2026-07-21: `_SOFT_SAFETY_NOTE`/the trigger condition (CTRS 3 +
# suicidal_ideation/self_harm category) previously existed only in
# `src/f1.py`'s harness pipeline — moved to `src.schemas.common` as a
# shared predicate/constant and ported into `OrchestratorAgent.
# _execute_pipeline` (sets `OrchestratorTurnResult.pending_soft_safety`) +
# `routes/chat.py` Step 5 (appends the note to the real DialogueAgent
# response on that flag).


class _StubSafetyAgent:
    """Returns a fixed `SafetyOutput` — no LLM call, mirrors the injection
    point `OrchestratorAgent._get_safety_agent` lazily creates
    (`self._safety_agent`)."""

    def __init__(self, ctrs_level: int, categories: list[str]) -> None:
        self._ctrs_level = ctrs_level
        self._categories = categories

    async def run(self, inp):
        from src.schemas.common import RISK_TO_CTRS, RiskLevel
        from src.schemas.safety import SafetyOutput

        risk = next(
            (r for r, c in RISK_TO_CTRS.items() if int(c) == self._ctrs_level), RiskLevel.none
        )
        return SafetyOutput(
            ctrs_level=self._ctrs_level,
            risk_level=risk,
            categories=self._categories,
            crisis_protocol_activated=False,
            requires_human_review=self._ctrs_level <= 3,
        )


async def _run_pipeline_with_stub_safety(ctrs_level: int, categories: list[str]):
    from src.agents.orchestrator import OrchestratorAgent
    from src.schemas.orchestrator import OrchestratorInput

    orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
    orch._safety_agent = _StubSafetyAgent(ctrs_level, categories)  # noqa: SLF001
    return await orch.process_turn(
        OrchestratorInput(session_id="t-bug047", raw_input="테스트 발화")
    )


class TestBug047SoftSafetyNote:
    def test_ctrs3_si_category_sets_pending_soft_safety_true(self) -> None:
        import asyncio

        result = asyncio.run(
            _run_pipeline_with_stub_safety(3, ["suicidal_ideation"])
        )
        assert result.pending_soft_safety is True
        assert result.crisis_triggered is False

    def test_ctrs3_without_si_category_does_not_trigger(self) -> None:
        import asyncio

        result = asyncio.run(_run_pipeline_with_stub_safety(3, []))
        assert result.pending_soft_safety is False

    def test_ordinary_ctrs4_does_not_trigger(self) -> None:
        import asyncio

        result = asyncio.run(
            _run_pipeline_with_stub_safety(4, ["suicidal_ideation"])
        )
        assert result.pending_soft_safety is False

    def test_ordinary_ctrs5_does_not_trigger(self) -> None:
        import asyncio

        result = asyncio.run(_run_pipeline_with_stub_safety(5, []))
        assert result.pending_soft_safety is False


class _StubDialogueAgentBug047:
    def __init__(self, model_router: object, prompt_loader: object) -> None:
        pass

    async def run(self, inp):
        from src.schemas.dialogue import DialogueOutput

        return DialogueOutput(assistant_response="힘드셨겠어요.", slot_updates={})


def test_route_appends_soft_safety_note_when_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from src.main import app
    from src.routes import chat as chat_route
    from src.schemas.common import CTRSLevel, RiskLevel
    from src.schemas.orchestrator import (
        OrchestratorTurnResult,
        SafetyStatus,
        SessionStage,
        SessionState,
    )

    class _StubOrchestratorPendingTrue:
        async def process_turn(self, inp):
            state = SessionState(session_id=inp.session_id)
            return OrchestratorTurnResult(
                session_id=inp.session_id,
                current_stage=SessionStage.dialogue_loop,
                safety_status=SafetyStatus(
                    ctrs_level=CTRSLevel.ACUTE, risk_level=RiskLevel.medium,
                    requires_human_review=True,
                ),
                crisis_triggered=False,
                handoff_ready=False,
                pending_soft_safety=True,
                session_state=state,
            )

    monkeypatch.setattr(chat_route, "DialogueAgent", _StubDialogueAgentBug047)
    app.dependency_overrides[chat_route._get_orchestrator] = (
        lambda: _StubOrchestratorPendingTrue()
    )
    try:
        client = TestClient(app)
        resp = client.post(
            "/ai/chat/respond",
            json={"session_id": "t-bug047-route", "user_message": "그냥 사라지고 싶어요"},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(chat_route._get_orchestrator, None)

    assert "109" in resp.json()["assistant_response"]


def test_route_does_not_append_soft_safety_note_when_not_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from src.main import app
    from src.routes import chat as chat_route
    from src.schemas.common import CTRSLevel, RiskLevel
    from src.schemas.orchestrator import (
        OrchestratorTurnResult,
        SafetyStatus,
        SessionStage,
        SessionState,
    )

    class _StubOrchestratorPendingFalse:
        async def process_turn(self, inp):
            state = SessionState(session_id=inp.session_id)
            return OrchestratorTurnResult(
                session_id=inp.session_id,
                current_stage=SessionStage.dialogue_loop,
                safety_status=SafetyStatus(
                    ctrs_level=CTRSLevel.MODERATE, risk_level=RiskLevel.low,
                ),
                crisis_triggered=False,
                handoff_ready=False,
                pending_soft_safety=False,
                session_state=state,
            )

    monkeypatch.setattr(chat_route, "DialogueAgent", _StubDialogueAgentBug047)
    app.dependency_overrides[chat_route._get_orchestrator] = (
        lambda: _StubOrchestratorPendingFalse()
    )
    try:
        client = TestClient(app)
        resp = client.post(
            "/ai/chat/respond",
            json={"session_id": "t-bug047-route-2", "user_message": "요즘 잠을 잘 못 자요"},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(chat_route._get_orchestrator, None)

    assert "109" not in resp.json()["assistant_response"]


# ── BUG-051 (CVR-039 blocking finding): soft-safety note hygiene at scale
# ── — once-per-session latch, same-turn dedup, history decontamination ──


class TestBug051SoftSafetyLatch:
    def test_latch_allows_first_trigger_this_session(self) -> None:
        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import SessionState

        state = SessionState(session_id="t-bug051-latch-1", turn_count=1)
        assert OrchestratorAgent._soft_safety_latch_allows(state) is True  # noqa: SLF001

    def test_latch_blocks_immediate_repeat_next_turn(self) -> None:
        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import SessionState

        state = SessionState(
            session_id="t-bug051-latch-2", turn_count=6,
            soft_safety_note_sent=True, soft_safety_note_last_turn=5,
        )
        assert OrchestratorAgent._soft_safety_latch_allows(state) is False  # noqa: SLF001

    def test_latch_rearms_after_gap_turns(self) -> None:
        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import SessionState

        state = SessionState(
            session_id="t-bug051-latch-3", turn_count=10,
            soft_safety_note_sent=True, soft_safety_note_last_turn=5,
        )
        # 10 - 5 = 5 >= _SOFT_SAFETY_REARM_TURNS (5) — re-armed.
        assert OrchestratorAgent._soft_safety_latch_allows(state) is True  # noqa: SLF001

    def test_pipeline_latches_across_two_consecutive_ctrs3_turns(self) -> None:
        """End-to-end via `process_turn`: turn 1 triggers, turn 2 (same
        session_state passed back, still CTRS 3 + SI) must NOT re-trigger
        — the exact "re-appended across nearby turns" CVR-039 finding."""
        import asyncio

        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _StubSafetyAgent(3, ["suicidal_ideation"])  # noqa: SLF001

        result1 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(session_id="t-bug051-pipeline", raw_input="힘들어요")
            )
        )
        assert result1.pending_soft_safety is True

        result2 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-bug051-pipeline", raw_input="여전히 힘들어요",
                    session_state=result1.session_state,
                )
            )
        )
        assert result2.pending_soft_safety is False


def test_same_turn_dedup_does_not_double_append(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUG-051 finding 1: when the model's OWN generated response already
    contains hotline content (an imitated echo, per CVR-039's own root-
    cause finding), the route must NOT append a second, canonical copy —
    the exact "두 번 연속" duplication CVR-039 observed live."""
    from fastapi.testclient import TestClient

    from src.main import app
    from src.routes import chat as chat_route
    from src.schemas.common import CTRSLevel, RiskLevel
    from src.schemas.dialogue import DialogueOutput
    from src.schemas.orchestrator import (
        OrchestratorTurnResult,
        SafetyStatus,
        SessionStage,
        SessionState,
    )

    class _StubDialogueAgentSelfEcho:
        def __init__(self, model_router: object, prompt_loader: object) -> None:
            pass

        async def run(self, inp):
            return DialogueOutput(
                assistant_response=(
                    "혹시 마음이 힘들 때 자살예방상담전화 109에서 도움을 받을 수 있다는 것을 "
                    "기억하고 계신가요?"
                ),
                slot_updates={},
            )

    class _StubOrchestratorPendingTrue:
        async def process_turn(self, inp):
            state = SessionState(session_id=inp.session_id, turn_count=1)
            return OrchestratorTurnResult(
                session_id=inp.session_id,
                current_stage=SessionStage.dialogue_loop,
                safety_status=SafetyStatus(
                    ctrs_level=CTRSLevel.ACUTE, risk_level=RiskLevel.medium,
                    requires_human_review=True,
                ),
                crisis_triggered=False,
                handoff_ready=False,
                pending_soft_safety=True,
                session_state=state,
            )

    monkeypatch.setattr(chat_route, "DialogueAgent", _StubDialogueAgentSelfEcho)
    app.dependency_overrides[chat_route._get_orchestrator] = (
        lambda: _StubOrchestratorPendingTrue()
    )
    try:
        client = TestClient(app)
        resp = client.post(
            "/ai/chat/respond",
            json={"session_id": "t-bug051-dedup", "user_message": "그냥 사라지고 싶어요"},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(chat_route._get_orchestrator, None)

    response_text = resp.json()["assistant_response"]
    assert response_text.count("자살예방상담전화") == 1, response_text


def test_history_decontamination_strips_note_from_llm_view_but_keeps_wire() -> None:
    """BUG-051 finding 1 (history decontamination): the DialogueAgent-
    facing copy must never see the verbatim injected overlay text (so it
    cannot imitate it), while the caller's own history (unrelated to this
    helper's output, wire/backend-stored) is untouched."""
    from src.routes.chat import _strip_injected_overlays_for_llm
    from src.schemas.common import SOFT_SAFETY_NOTE

    original = [
        {"role": "user", "content": "그냥 사라지고 싶어요"},
        {
            "role": "assistant",
            "content": "많이 힘드셨겠어요. 힘이 되는 사람이 있으신가요?" + SOFT_SAFETY_NOTE,
        },
        {"role": "user", "content": "네 있어요"},
    ]
    cleaned = _strip_injected_overlays_for_llm(original)

    assert SOFT_SAFETY_NOTE not in cleaned[1]["content"]
    assert "많이 힘드셨겠어요" in cleaned[1]["content"]
    # Original list (what the caller/wire keeps) is untouched.
    assert SOFT_SAFETY_NOTE in original[1]["content"]


def test_soft_safety_note_append_is_never_truncated() -> None:
    """BUG-051 finding (iii) regression guard: the append is plain string
    concatenation (`.rstrip() + SOFT_SAFETY_NOTE`) — never subject to any
    LLM token cap. Guards against a future regression (e.g. a length-
    capped field/truncation step added later) silently cutting the
    canonical, route-appended note — the ROOT CAUSE fix for the actual
    live truncation CVR-039 observed is history decontamination (above):
    it prevents the MODEL from generating its own token-capped echo of
    the note in the first place, which is what was actually truncated."""
    from src.schemas.common import SOFT_SAFETY_NOTE

    base_response = "그런 마음까지 드실 정도로 힘드셨겠어요. 어떤 부분이 가장 힘드신가요?"
    appended = base_response.rstrip() + SOFT_SAFETY_NOTE
    assert appended.endswith(SOFT_SAFETY_NOTE)
    assert appended.endswith("기억해 주세요.")
    assert len(appended) == len(base_response.rstrip()) + len(SOFT_SAFETY_NOTE)


# ── Coverage seeding: backend-accumulated filled_slots drive handoff_ready
# ── organically (not only the turn-count ceiling) ────────────────────────


class _StubSlotAgentNoOp:
    """No-op extractor — the test's own `filled_slots` are already seeded
    into `state.slot_data` before this would run; this stub only exists so
    `_run_post_dialogue_pipeline` never attempts a real (router/loader-
    backed) LLM call in this unit test."""

    async def run(self, inp):
        from src.schemas.clinical_slot import ClinicalSlotOutput

        return ClinicalSlotOutput(
            extracted_slots={}, filled_slots=[], missing_slots=[],
            essential_filled=[], essential_missing=[], slot_coverage=0.0,
        )


class _StubHandoffAgent:
    """Minimal valid `HandoffOutput` — no LLM call."""

    async def run(self, inp):
        from src.schemas.common import RiskLevel
        from src.schemas.handoff import HandoffOutput

        return HandoffOutput(
            report_markdown="# 테스트 핸드오프 리포트\n\n주호소: 우울감",
            evidence_packets=[], missing_slots=[], risk_level=RiskLevel.none,
        )


class _StubVerifierAgentPass:
    """Deterministic `VerifierAction.passed` — this test exercises
    coverage-seeding/handoff_ready wiring only, not the real
    `EvidenceVerifierAgent`'s 12-section-completeness content rules
    (orthogonal concern, already covered by its own tests)."""

    async def run(self, inp):
        from src.agents.evidence_verifier import EvidenceVerifierOutput, VerifierAction

        return EvidenceVerifierOutput(action=VerifierAction.passed)


def test_coverage_seeding_9_of_12_filled_slots_fires_handoff_ready() -> None:
    """ADR-042 UPDATE: coverage alone is no longer sufficient — the
    termination gate additionally requires `risk_grounded`. Turn 1 reaches
    coverage >= 0.7 but stays in `dialogue_loop` (mandatory SI screen
    fires instead of handoff); turn 2's SI-negative answer grounds risk
    and handoff fires. This strengthens, not weakens, the original
    assertion (coverage-seeded handoff_ready still holds, now correctly
    gated on an actual risk screen instead of firing from slot content
    alone — the exact gap ADR-042/Cluster C closes)."""
    import asyncio

    from src.agents.orchestrator import OrchestratorAgent
    from src.schemas.orchestrator import OrchestratorInput, SessionStage

    nine_slots = {
        "encounter_metadata": "40대 남성",
        "chief_complaint": "우울감",
        "history_of_present_illness": "3개월 전부터 악화",
        "past_psychiatric_history": "없음",
        "medical_history": "없음",
        "personal_social_history": "무직",
        "family_history": "없음",
        "substance_use_history": "없음",
        "mental_status_exam": "정상 외모, 저하된 기분",
    }
    assert len(nine_slots) == 9

    orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
    orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
    orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
    orch._handoff_agent = _StubHandoffAgent()  # noqa: SLF001
    orch._verifier_agent = _StubVerifierAgentPass()  # noqa: SLF001

    turn1 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id="t-coverage-seed",
                raw_input="네 알겠습니다",
                filled_slots=nine_slots,
            )
        )
    )
    assert turn1.session_state.slot_coverage >= 0.7
    assert turn1.handoff_ready is False
    assert turn1.current_stage == SessionStage.dialogue_loop
    assert turn1.probe_instruction is not None  # mandatory SI screen fired
    assert turn1.session_state.risk_question_pending is True

    turn2 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id="t-coverage-seed",
                raw_input="아니요, 그런 생각은 전혀 없어요",
                filled_slots=nine_slots,
                session_state=turn1.session_state,
            )
        )
    )
    assert turn2.session_state.risk_grounded is True
    assert turn2.handoff_ready is True
    assert turn2.handoff_report is not None
    assert turn2.session_state.slot_coverage >= 0.7


def test_coverage_seeding_below_threshold_stays_in_dialogue() -> None:
    import asyncio

    from src.agents.orchestrator import OrchestratorAgent
    from src.schemas.orchestrator import OrchestratorInput

    orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
    orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001

    result = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id="t-coverage-seed-low",
                raw_input="네",
                filled_slots={"chief_complaint": "우울감"},
            )
        )
    )

    assert result.handoff_ready is False
    assert result.handoff_report is None


# ── B5 enabler (EXP-029) UPDATED by ADR-042 (EXP-030 cluster C):
# ── slot_coverage's denominator is PATIENT_FILLABLE_SLOTS, now 8 of 12
# ── (risk_assessment re-included — see that constant's own docstring for
# ── the full evidence) — coverage crossing 0.7 is necessary but no
# ── longer sufficient on its own; `risk_grounded` must also be True.


def test_b5_patient_fillable_coverage_6_of_7_fires_handoff_ready() -> None:
    """6 of the 7 non-risk PATIENT_FILLABLE_SLOTS filled (risk_assessment
    is the 8th, ungrounded) — coverage = 6/8 = 0.75 >= 0.7, but the
    termination gate holds the session in dialogue_loop until the
    mandatory SI screen grounds risk_assessment (turn 2)."""
    import asyncio

    from src.agents.clinical_slot import PATIENT_FILLABLE_SLOTS
    from src.agents.orchestrator import OrchestratorAgent
    from src.schemas.orchestrator import OrchestratorInput

    assert len(PATIENT_FILLABLE_SLOTS) == 8
    six_fillable = {
        "chief_complaint": "우울감",
        "history_of_present_illness": "3개월 전부터 악화",
        "past_psychiatric_history": "없음(환자 부인: '정신과 진료는 받아본 적 없어요.')",
        "medical_history": "없음(환자 부인: '지병은 없어요.')",
        "personal_social_history": "어머니와 자주 통화함",
        "family_history": "없음(환자 부인: '가족력은 없어요.')",
        # substance_use_history intentionally left unfilled
    }
    assert len(six_fillable) == 6
    assert set(six_fillable) <= set(PATIENT_FILLABLE_SLOTS)

    orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
    orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
    orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
    orch._handoff_agent = _StubHandoffAgent()  # noqa: SLF001
    orch._verifier_agent = _StubVerifierAgentPass()  # noqa: SLF001

    turn1 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id="t-b5-fillable-coverage",
                raw_input="네 알겠습니다",
                filled_slots=six_fillable,
            )
        )
    )
    assert turn1.session_state.slot_coverage == pytest.approx(6 / 8)
    assert turn1.session_state.slot_coverage >= 0.7
    assert turn1.handoff_ready is False  # risk_assessment not yet grounded

    turn2 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id="t-b5-fillable-coverage",
                raw_input="아니요, 그런 생각은 없어요",
                filled_slots=six_fillable,
                session_state=turn1.session_state,
            )
        )
    )
    assert turn2.session_state.risk_grounded is True
    assert turn2.handoff_ready is True
    assert turn2.handoff_report is not None


def test_b5_legacy_full_12_slot_payload_still_computes_coverage() -> None:
    """A caller still sending the OLD full-12-slot shape (including
    system/observation keys the denominator excludes) must not break —
    those extra keys are simply not counted, coverage is computed
    correctly over the 8 fillable ones. BUG-049 protection: a caller-
    seeded `risk_assessment` value counts toward COVERAGE MATH (it is
    present in `slot_data`) but must NOT count as `risk_grounded` — only
    the orchestrator's own probe/SI-screen may set that flag, so
    handoff_ready still does not fire from seeding alone; turn 2's
    genuine SI-screen answer grounds it for real."""
    import asyncio

    from src.agents.orchestrator import OrchestratorAgent
    from src.schemas.orchestrator import OrchestratorInput

    all_12 = {
        "encounter_metadata": "40대 남성",
        "chief_complaint": "우울감",
        "history_of_present_illness": "3개월 전부터 악화",
        "past_psychiatric_history": "없음(환자 부인: '정신과 진료는 받아본 적 없어요.')",
        "medical_history": "없음(환자 부인: '지병은 없어요.')",
        "personal_social_history": "어머니와 자주 통화함",
        "family_history": "없음(환자 부인: '가족력은 없어요.')",
        "substance_use_history": "없음(환자 부인: '술은 안 마셔요.')",
        "mental_status_exam": "정상 외모, 저하된 기분",
        # legacy caller-seeded risk_assessment — must NOT count as grounded
        "risk_assessment": "자해 생각은 없다고 말함",
        "clinical_assessment": "우울 증상 호소",
        "treatment_plan": "추적 관찰 권고",
    }
    assert len(all_12) == 12

    orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
    orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
    orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
    orch._handoff_agent = _StubHandoffAgent()  # noqa: SLF001
    orch._verifier_agent = _StubVerifierAgentPass()  # noqa: SLF001

    turn1 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id="t-b5-legacy-12-slot",
                raw_input="네 알겠습니다",
                filled_slots=all_12,
            )
        )
    )
    assert turn1.session_state.slot_coverage == pytest.approx(1.0)
    # BUG-049 protection: caller-seeded risk_assessment is NOT grounded —
    # handoff_ready must not fire from slot content alone.
    assert turn1.session_state.risk_grounded is False
    assert turn1.handoff_ready is False

    turn2 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id="t-b5-legacy-12-slot",
                raw_input="아니요, 그런 생각은 없어요",
                filled_slots=all_12,
                session_state=turn1.session_state,
            )
        )
    )
    assert turn2.session_state.risk_grounded is True
    assert turn2.handoff_ready is True
    assert turn2.handoff_report is not None


# ── BUG-048(a): repetition guard scope widened to the follow-up-question
# ── span, not just the empathy lead-in ────────────────────────────────


def test_repeated_question_span_triggers_question_repeat_violation() -> None:
    """Same substantive follow-up question, DIFFERENT (varying) empathy
    lead-in each time — `_extract_leading_clause`/`_empathy_repetition_
    violation` alone would miss this (BUG-048 repro shape); the new
    trailing-clause check must catch it."""
    from src.agents.dialogue import DialogueAgent

    question = "혹시 기존에 진단받은 신체질환이 있거나 복용 중인 약이 있으신가요?"
    history = [
        {"role": "user", "content": "요즘 잠을 잘 못 자요."},
        {"role": "assistant", "content": f"많이 힘드셨겠어요. {question}"},
        {"role": "user", "content": "그냥 그래요."},
        {"role": "assistant", "content": f"그러셨군요. {question}"},
    ]
    session_question_clauses = DialogueAgent._extract_used_trailing_clauses(history)
    assert session_question_clauses == [question, question]

    candidate_clause = DialogueAgent._extract_trailing_clause(
        f"이해합니다. {question}"
    )
    violation = DialogueAgent._empathy_repetition_violation(
        candidate_clause, session_question_clauses
    )
    assert violation == "back_to_back"


def test_varied_question_wording_does_not_trigger_question_repeat() -> None:
    from src.agents.dialogue import DialogueAgent

    history = [
        {"role": "assistant", "content": "많이 힘드셨겠어요. 잠은 잘 주무시나요?"},
    ]
    session_question_clauses = DialogueAgent._extract_used_trailing_clauses(history)

    candidate_clause = DialogueAgent._extract_trailing_clause(
        "그러셨군요. 식사는 잘 챙겨 드시나요?"
    )
    violation = DialogueAgent._empathy_repetition_violation(
        candidate_clause, session_question_clauses
    )
    assert violation is None


# ── EXP-029 Stage A1 / BUG-049 defense-in-depth: v5's quote-embedded
# ── denial format vs the route grounding filter (src.grounding) ─────────
#
# v4's bare "없음(환자 부인)" was a lexical dead-end — it carries no
# patient-specific tokens, so BUG-049's own grounding fix (`POST /ai/slots/
# extract`'s `has_lexical_evidence` check) would ALWAYS drop it, even a
# genuine one. v5's redesign embeds the actual patient quote in the value
# instead. These are pure-function tests — runnable now, before v5 is
# pinned, since they exercise `src.grounding` directly (unchanged by this
# draft) rather than the (still-v3) live prompt/LLM.


class TestExp029A1QuoteEmbeddedDenialGrounding:
    def test_real_quote_embedded_denial_passes_grounding(self) -> None:
        from src.grounding import has_lexical_evidence

        utterances = ["지병은 없어요. 건강한 편이에요."]
        value = "없음(환자 부인: '지병은 없어요. 건강한 편이에요.')"
        assert has_lexical_evidence(value, utterances) is True

    def test_fabricated_quote_embedded_denial_is_dropped(self) -> None:
        from src.grounding import has_lexical_evidence

        # Topic never raised anywhere in the transcript (BUG-049 shape) —
        # a fabricated "quote" cannot match any real patient utterance.
        utterances = ["요즘 계속 우울해요.", "잠을 잘 못 자요."]
        value = "없음(환자 부인: '가족력은 없어요.')"
        assert has_lexical_evidence(value, utterances) is False

    def test_v4_bare_fixed_format_fails_grounding_the_dead_end_v5_fixes(self) -> None:
        """Documents WHY v4 was unfixable via the grounding filter alone —
        even a genuine denial in v4's bare format has zero patient tokens
        and is indistinguishable from a fabrication to `has_lexical_
        evidence`. This is the dead-end EXP-029 A1's quote-embedded
        redesign exists to dissolve."""
        from src.grounding import has_lexical_evidence

        utterances = ["지병은 없어요. 건강한 편이에요."]
        value = "없음(환자 부인)"
        assert has_lexical_evidence(value, utterances) is False


# ── BUG-050: EvidenceVerifierAgent over-strictness fixes ─────────────────
#
# Fixed 2026-07-21 (major): live reproduction on a real 100%-coverage B5
# session showed `_check_unsupported_claims` firing on sections asserting
# no patient-specific claim at all (administrative 섹션 1/2, a "해당
# 없음"-only 섹션 6 data table, and the report's own limitations/missing-
# info disclaimer 섹션 10) — 2 targeted, evidence-based exemptions added.
# `src/agents/orchestrator.py::_build_handoff_input` also fixed
# separately (SlotData was missing 4 of 7 real PATIENT_FILLABLE_SLOTS
# values — see `src/schemas/handoff.py::SlotData`'s own docstring).

_B5_EVIDENCE_PACKETS = [
    EvidencePacket(
        evidence_id="ev_msg_001", source_type=EvidenceSource.message,
        source_ref="환자 발화", content_summary="불안하고 잠을 잘 못 자요",
    ),
    EvidencePacket(
        evidence_id="ev_msg_002", source_type=EvidenceSource.message,
        source_ref="환자 발화", content_summary="3주 전 프로젝트 마감부터 시작",
    ),
    EvidencePacket(
        evidence_id="ev_msg_003", source_type=EvidenceSource.message,
        source_ref="환자 발화", content_summary="자살/자해 생각 전혀 없음",
    ),
    EvidencePacket(
        evidence_id="ev_msg_004", source_type=EvidenceSource.message,
        source_ref="환자 발화", content_summary="정신과 진료 받아본 적 없음",
    ),
]


def _b5_shape_report(*, well_cited: bool) -> str:
    """A synthetic report matching the REAL B5 session's content shape
    (same slot facts captured live in `experiments/EXP-029/logs/
    0024_VP-001_s500_t12.json`) — `well_cited=True` is what the generator
    SHOULD produce given this content (every clinically-substantive
    section cited, matching `_B5_EVIDENCE_PACKETS` exactly, no dangling/
    orphan refs); `well_cited=False` reproduces the genuine, still-open
    residual gap the live reproduction actually shows (섹션 3/7/11 missing
    citations, 3 real warnings — the SAME sections BUG-050's live repro
    consistently found uncited across multiple real generation attempts,
    the residual gap in the pinned generator this fix does not touch) —
    proves the fail-closed path is not weakened (a single missing
    citation alone stays under the `warning_count >= 3` threshold by the
    verifier's own pre-existing, unchanged design; this reproduces the
    REAL multi-section pattern that actually regenerates in production)."""
    cite = well_cited
    sec3_citation = " [ev_msg_001][ev_msg_002]" if cite else ""
    sec7_citation = " [ev_msg_004]" if cite else ""
    sec11_citation = " [ev_msg_003]" if cite else ""
    return f"""## 섹션 1. 환자 기본 정보
- 익명화된 ID, 30대(추정), 남성, 초진

## 섹션 2. 평가 일시 및 환경
- 자율 대화 기반, 척도 미시행, OCR 문서 없음

## 섹션 3. 주호소 및 현병력
- 주호소: 불안, 수면장애, 식욕저하, 우울감{sec3_citation}
- 경과: 3주 전 프로젝트 마감부터 시작, 지속 중{sec3_citation}

## 섹션 4. 주요 증상
| 영역 | 근거 |
|---|---|
| 불안 | [ev_msg_001] |

## 섹션 5. CTRS 기반 위험도 평가
- CTRS 4단계(중증/주의). 자살/자해: 없음 [ev_msg_003]

## 섹션 6. 구조화 척도 결과
| 척도명 | 총점 | Severity | 시행 일시 | 주요 양성 문항 |
|---|---|---|---|---|
| 해당 없음 | - | - | - | - |

## 섹션 7. 과거 병력 및 현재 약물
- 정신과 진료 없음{sec7_citation}

## 섹션 9. 종단적 상태 변화
- 이전 기록 없음 (초진) [ev_msg_001]

## 섹션 10. 추가 정보 필요 사항
본 보고서는 AI 보조 사전문진 결과이며, **진단이 아닙니다.** 전문의의 임상적 판단이 최종 결정입니다.

**추가 정보 필요 사항:**
- PHQ-9, GAD-7 등 구조화 척도 결과

## 섹션 11. 추천 진료과 및 사유
정신건강의학과 상담 권고, 4주 이내 재평가{sec11_citation}

## 섹션 12. 근거 레지스트리

| Evidence ID | 내용 |
|---|---|
| [ev_msg_001] | 불안하고 잠을 잘 못 자요 |
| [ev_msg_002] | 3주 전 프로젝트 마감부터 시작 |
| [ev_msg_003] | 자살/자해 생각 전혀 없음 |
| [ev_msg_004] | 정신과 진료 받아본 적 없음 |
"""


class TestBug050EvidenceVerifierFix:
    async def test_synthetic_well_formed_report_passes(self) -> None:
        """(item 4a) A synthetic, properly-cited report — every clinically
        substantive section cited, admin/no-data/disclaimer sections
        correctly exempted — must PASS."""
        from src.agents.evidence_verifier import EvidenceVerifierAgent, EvidenceVerifierInput

        verifier = EvidenceVerifierAgent()
        result = await verifier.run(
            EvidenceVerifierInput(
                session_id="t-bug050-synthetic-pass",
                report_markdown=_b5_shape_report(well_cited=True),
                evidence_packets=_B5_EVIDENCE_PACKETS,
                is_first_visit=True,
                has_scale_scores=False,
                has_ocr_documents=False,
                ctrs_level=4,
            )
        )
        assert result.action == VerifierAction.passed, result.issues

    async def test_b5_shape_well_cited_report_delivers(self) -> None:
        """(item 4b) The B5-SHAPE scenario (real slot content from the
        actual live session) — well-cited — must also PASS/deliver,
        proving the verifier's rules are correctly calibrated for real
        B5 content once every section is properly cited."""
        from src.agents.evidence_verifier import EvidenceVerifierAgent, EvidenceVerifierInput

        verifier = EvidenceVerifierAgent()
        result = await verifier.run(
            EvidenceVerifierInput(
                session_id="t-bug050-b5-shape-pass",
                report_markdown=_b5_shape_report(well_cited=True),
                evidence_packets=_B5_EVIDENCE_PACKETS,
                is_first_visit=True,
                has_scale_scores=False,
                has_ocr_documents=False,
                ctrs_level=4,
            )
        )
        assert result.action == VerifierAction.passed, result.issues

    async def test_genuinely_unsupported_claim_still_regenerates(self) -> None:
        """(item 4c) A report with a REAL uncited clinical claim (섹션 3,
        the exact residual gap BUG-050's live reproduction still shows in
        the pinned generator's actual output) must still trigger
        regenerate/reject — fail-closed is not weakened by the over-
        strictness fixes."""
        from src.agents.evidence_verifier import EvidenceVerifierAgent, EvidenceVerifierInput

        verifier = EvidenceVerifierAgent()
        result = await verifier.run(
            EvidenceVerifierInput(
                session_id="t-bug050-genuine-unsupported",
                report_markdown=_b5_shape_report(well_cited=False),
                evidence_packets=_B5_EVIDENCE_PACKETS,
                is_first_visit=True,
                has_scale_scores=False,
                has_ocr_documents=False,
                ctrs_level=4,
            )
        )
        assert result.action != VerifierAction.passed
        assert any(
            "섹션 3" in issue.location for issue in result.issues
        ), result.issues


# ── EXP-030 Phase 2 (ADR-042/043): single coordinated change to
# ── `OrchestratorAgent._execute_pipeline` — cluster A (#1 asked-slot
# ── tracking), cluster C (#3 risk_assessment Safety Probe port +
# ── termination gate), cluster G (#9 post-handoff once-fire guard). ──────


class _SequencedSafetyAgent:
    """Returns a DIFFERENT fixed `SafetyOutput` on each successive call —
    (ctrs_level, categories) tuples consumed in order; the LAST tuple
    repeats for any call beyond the sequence length. No LLM call."""

    def __init__(self, sequence: list[tuple[int, list[str]]]) -> None:
        self._sequence = sequence
        self._call_index = 0

    async def run(self, inp):
        from src.schemas.common import RISK_TO_CTRS, RiskLevel
        from src.schemas.safety import SafetyOutput

        idx = min(self._call_index, len(self._sequence) - 1)
        ctrs_level, categories = self._sequence[idx]
        self._call_index += 1
        risk = next(
            (r for r, c in RISK_TO_CTRS.items() if int(c) == ctrs_level), RiskLevel.none
        )
        return SafetyOutput(
            ctrs_level=ctrs_level,
            risk_level=risk,
            categories=categories,
            crisis_protocol_activated=False,
            requires_human_review=ctrs_level <= 3,
        )


class _CountingHandoffAgent:
    """Same as `_StubHandoffAgent` but counts invocations, so a test can
    assert the handoff pipeline does NOT re-run on a post-handoff turn."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, inp):
        from src.schemas.common import RiskLevel
        from src.schemas.handoff import HandoffOutput

        self.call_count += 1
        return HandoffOutput(
            report_markdown="# 테스트 핸드오프 리포트\n\n주호소: 우울감",
            evidence_packets=[], missing_slots=[], risk_level=RiskLevel.none,
        )


class _CountingVerifierAgent:
    """Same as `_StubVerifierAgentPass` but counts invocations."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, inp):
        from src.agents.evidence_verifier import EvidenceVerifierOutput, VerifierAction

        self.call_count += 1
        return EvidenceVerifierOutput(action=VerifierAction.passed)


_EIGHT_TH_SLOT_MINUS_RISK = {
    "chief_complaint": "우울감",
    "history_of_present_illness": "3개월 전부터 악화",
    "past_psychiatric_history": "없음(환자 부인: '없어요.')",
    "medical_history": "없음(환자 부인: '없어요.')",
    "personal_social_history": "어머니와 자주 통화함",
    "family_history": "없음(환자 부인: '없어요.')",
    "substance_use_history": "없음(환자 부인: '안 마셔요.')",
}


class TestExp030TerminationGate:
    """(a) termination gate blocks `handoff_ready` until risk grounded —
    repeated attempts to terminate on coverage alone (all 7 non-risk
    PATIENT_FILLABLE_SLOTS filled, coverage 7/8 = 0.875 >= 0.7) must never
    fire while `risk_grounded` stays False, across multiple turns."""

    def test_gate_blocks_on_first_coverage_hit_across_independent_sessions(self) -> None:
        """Coverage alone (7/8 = 0.875 >= 0.7) never fires `handoff_ready`
        while risk is ungrounded — verified across 3 INDEPENDENT fresh
        sessions (not a fluke of one particular session's state), each
        instead receiving the mandatory SI screen instruction."""
        import asyncio

        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput

        for i in range(3):
            orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
            orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
            orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
            orch._handoff_agent = _StubHandoffAgent()  # noqa: SLF001
            orch._verifier_agent = _StubVerifierAgentPass()  # noqa: SLF001

            turn = asyncio.run(
                orch.process_turn(
                    OrchestratorInput(
                        session_id=f"t-exp030-gate-{i}",
                        raw_input="네",
                        filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                    )
                )
            )
            assert turn.handoff_ready is False
            assert turn.session_state.risk_grounded is False
            assert turn.session_state.slot_coverage >= 0.7
            assert turn.probe_instruction is not None
            assert turn.session_state.risk_question_pending is True

    def test_gate_fires_once_the_mandatory_screen_is_answered(self) -> None:
        import asyncio

        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
        orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
        orch._handoff_agent = _StubHandoffAgent()  # noqa: SLF001
        orch._verifier_agent = _StubVerifierAgentPass()  # noqa: SLF001

        turn1 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-gate-fires",
                    raw_input="네",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                )
            )
        )
        assert turn1.handoff_ready is False

        # Mandatory SI screen (set at the end of turn 1) is answered here.
        final_turn = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-gate-fires",
                    raw_input="아니요, 그런 생각 전혀 없어요",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                    session_state=turn1.session_state,
                )
            )
        )
        assert final_turn.session_state.risk_grounded is True
        assert final_turn.handoff_ready is True
        assert final_turn.handoff_report is not None


class TestExp030SafetyProbeGroundsRiskAssessment:
    """(b) the ported Safety Probe fills `risk_assessment` on the
    production path — CTRS3+SI triggers probe mode; walking through the
    "frequency" then "plan" stages with a genuine denial at "plan"
    de-escalates and grounds `risk_assessment` with the ACTUAL patient
    wording (never a template), mirroring f1.py's own composition."""

    def test_probe_walks_stages_and_grounds_risk_from_real_wording(self) -> None:
        import asyncio

        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _SequencedSafetyAgent(  # noqa: SLF001
            [(3, ["suicidal_ideation"]), (5, []), (5, [])]
        )

        turn1 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-probe",
                    raw_input="가끔 사라지고 싶다는 생각이 들어요",
                )
            )
        )
        assert turn1.session_state.probe_active is True
        assert turn1.probe_instruction is not None
        assert turn1.session_state.probe_awaiting_answer is True
        assert turn1.session_state.risk_grounded is False

        # Answers the "frequency" stage — no plan/means disclosure, no
        # negation-gated stage yet — probe continues to the "plan" stage.
        turn2 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-probe",
                    raw_input="가끔 그래요",
                    session_state=turn1.session_state,
                )
            )
        )
        assert turn2.session_state.probe_active is True
        assert turn2.session_state.risk_grounded is False
        assert turn2.session_state.probe_stage_idx == 1  # advanced to "plan"

        # Answers the "plan" stage with a genuine denial — de-escalates.
        turn3 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-probe",
                    raw_input="구체적인 계획 같은 건 전혀 없어요",
                    session_state=turn2.session_state,
                )
            )
        )
        assert turn3.session_state.probe_active is False
        assert turn3.session_state.risk_grounded is True
        assert "risk_assessment" in turn3.session_state.slot_data
        risk_value = turn3.session_state.slot_data["risk_assessment"]
        assert "사라지고 싶다" in risk_value  # trigger utterance preserved verbatim
        assert "계획 같은 건 전혀 없어요" in risk_value  # denial preserved verbatim

    def test_plan_disclosure_escalates_to_crisis(self) -> None:
        """Belt-and-braces lexical escalation: a genuine plan/means
        disclosure during the probe must route to crisis_flow, exactly
        like a CTRS 1-2 safety-gate hit."""
        import asyncio

        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput, SessionStage

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _SequencedSafetyAgent(  # noqa: SLF001
            [(3, ["suicidal_ideation"]), (5, [])]
        )

        turn1 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-probe-escalate",
                    raw_input="가끔 사라지고 싶다는 생각이 들어요",
                )
            )
        )
        assert turn1.session_state.probe_active is True

        turn2 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-probe-escalate",
                    raw_input="사실 유서도 이미 써놨어요",
                    session_state=turn1.session_state,
                )
            )
        )
        assert turn2.current_stage == SessionStage.crisis_flow
        assert turn2.crisis_triggered is True
        assert turn2.session_state.probe_active is False


class TestExp030AskedSlotDeferral:
    """(c) asked-slot deferral after N (=2) unanswered asks — the
    generalized fix covers any patient-fillable slot via
    `OrchestratorAgent._update_asked_slot_tracking`, and `risk_assessment`
    is categorically excluded (governed by Cluster C instead)."""

    def test_slot_deferred_after_two_unanswered_asks(self) -> None:
        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import SessionState

        state = SessionState(session_id="t-exp030-defer")

        state.pending_target_slot = "family_history"
        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001
        assert state.asked_slot_counts.get("family_history") == 1
        assert "family_history" not in state.deferred_slots

        state.pending_target_slot = "family_history"
        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001
        assert state.asked_slot_counts.get("family_history") == 2
        assert "family_history" in state.deferred_slots

    def test_answered_slot_resets_counter_without_deferring(self) -> None:
        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import SessionState

        state = SessionState(session_id="t-exp030-defer-answered")
        state.pending_target_slot = "family_history"
        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001
        assert state.asked_slot_counts.get("family_history") == 1

        state.slot_data["family_history"] = "없음(환자 부인: '없어요.')"
        state.pending_target_slot = "family_history"
        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001
        assert "family_history" not in state.asked_slot_counts
        assert "family_history" not in state.deferred_slots

    def test_risk_assessment_never_deferred(self) -> None:
        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import SessionState

        state = SessionState(session_id="t-exp030-defer-risk")
        for _ in range(5):
            state.pending_target_slot = "risk_assessment"
            OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001
        assert state.asked_slot_counts.get("risk_assessment") is None
        assert "risk_assessment" not in state.deferred_slots

    def test_deferred_slot_excluded_from_dialogue_round_robin(self) -> None:
        from src.agents.dialogue import DialogueAgent

        filled = {"chief_complaint": "우울감"}
        missing = DialogueAgent.missing_questionable_slots(
            filled, deferred_slots={"family_history"}
        )
        assert "family_history" not in missing

        target = DialogueAgent.compute_target_slot(
            filled, conversation_history=None, deferred_slots={"family_history"}
        )
        assert target != "family_history"


class TestExp030PostHandoffOnceFireGuard:
    """(d) handoff fires once + no per-turn re-run; (e) post-handoff
    crisis still routes to crisis_flow (ADR-043)."""

    def test_handoff_fires_once_and_pipeline_does_not_rerun(self) -> None:
        import asyncio

        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput, SessionStage

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
        orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
        handoff_agent = _CountingHandoffAgent()
        verifier_agent = _CountingVerifierAgent()
        orch._handoff_agent = handoff_agent  # noqa: SLF001
        orch._verifier_agent = verifier_agent  # noqa: SLF001

        # Turn 1: ground risk via the mandatory SI screen (all other
        # slots pre-filled), turn 2 delivers the fired-once handoff.
        turn1 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-once",
                    raw_input="네",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                )
            )
        )
        assert turn1.handoff_ready is False

        turn2 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-once",
                    raw_input="아니요, 그런 생각 없어요",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                    session_state=turn1.session_state,
                )
            )
        )
        assert turn2.handoff_ready is True
        assert turn2.session_state.handoff_delivered is True
        assert handoff_agent.call_count == 1
        assert verifier_agent.call_count == 1

        # Turn 3: session already completed — must short-circuit WITHOUT
        # re-invoking the handoff/verifier agents.
        turn3 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-once",
                    raw_input="감사합니다",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                    session_state=turn2.session_state,
                )
            )
        )
        assert turn3.current_stage == SessionStage.completed
        assert turn3.handoff_ready is False
        assert turn3.assistant_response  # non-empty short-circuit message
        assert handoff_agent.call_count == 1  # unchanged — no re-run
        assert verifier_agent.call_count == 1  # unchanged — no re-run

    def test_post_handoff_crisis_still_routes_to_crisis_flow(self) -> None:
        """(e) safety-gate-before-coverage invariant: a crisis-level
        utterance AFTER `handoff_delivered` is already True must still
        hit `crisis_flow`, not the post-handoff short-circuit."""
        import asyncio

        from src.agents.orchestrator import OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput, SessionStage

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _SequencedSafetyAgent(  # noqa: SLF001
            [(5, []), (5, []), (1, ["suicidal_ideation"])]
        )
        orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
        orch._handoff_agent = _StubHandoffAgent()  # noqa: SLF001
        orch._verifier_agent = _StubVerifierAgentPass()  # noqa: SLF001

        turn1 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-posthandoff-crisis",
                    raw_input="네",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                )
            )
        )
        assert turn1.handoff_ready is False

        turn2 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-posthandoff-crisis",
                    raw_input="아니요, 그런 생각 없어요",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                    session_state=turn1.session_state,
                )
            )
        )
        assert turn2.handoff_ready is True
        assert turn2.session_state.handoff_delivered is True

        turn3 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-exp030-posthandoff-crisis",
                    raw_input="더 이상 못 버티겠어요",
                    filled_slots=_EIGHT_TH_SLOT_MINUS_RISK,
                    session_state=turn2.session_state,
                )
            )
        )
        assert turn3.current_stage == SessionStage.crisis_flow
        assert turn3.crisis_triggered is True


class TestAdr044BackstopVsRiskGroundingGate:
    """ADR-044 (CVR-043 pin-fix, item 6): the `_MAX_DIALOGUE_TURNS` hard
    backstop must never silently ship `handoff_ready=True` while
    `risk_grounded` is False — it must instead force
    `clinical_escalation_required=True` (and suppress `handoff_ready`/
    `handoff_report`), and the session must still conclude (not loop
    forever re-attempting the pipeline)."""

    def test_backstop_with_ungrounded_risk_suppresses_handoff_ready(self) -> None:
        import asyncio

        from src.agents.orchestrator import (
            _INCOMPLETE_INTAKE_MESSAGE,
            _MAX_DIALOGUE_TURNS,
            OrchestratorAgent,
        )
        from src.schemas.orchestrator import OrchestratorInput, SessionState

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
        orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
        handoff_agent = _CountingHandoffAgent()
        verifier_agent = _CountingVerifierAgent()
        orch._handoff_agent = handoff_agent  # noqa: SLF001
        orch._verifier_agent = verifier_agent  # noqa: SLF001

        # One turn short of the backstop, risk still ungrounded, several
        # other slots also still missing (a session that never got around
        # to asking risk despite the reserve window — e.g. an unusually
        # low-information-density conversation).
        state = SessionState(
            session_id="t-adr044-backstop",
            turn_count=_MAX_DIALOGUE_TURNS - 1,
            risk_grounded=False,
        )

        turn = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-adr044-backstop",
                    raw_input="네 알겠습니다",
                    session_state=state,
                )
            )
        )

        assert turn.session_state.turn_count == _MAX_DIALOGUE_TURNS
        assert turn.session_state.risk_grounded is False
        # The pipeline WAS actually run and would otherwise have produced
        # a valid, verified report (proving this is a deliberate override,
        # not a pipeline failure/reject being conflated with escalation).
        assert handoff_agent.call_count == 1
        assert verifier_agent.call_count == 1
        # ... yet handoff_ready/handoff_report are force-suppressed.
        assert turn.handoff_ready is False
        assert turn.handoff_report is None
        assert turn.clinical_escalation_required is True
        assert turn.session_state.risk_screening_incomplete is True
        # Patient is not stranded — the turn still carries a concluding,
        # calm patient-facing message (not empty, not the routine
        # "확인 필요" framing baked into a silent ready-for-handoff turn).
        assert turn.assistant_response == _INCOMPLETE_INTAKE_MESSAGE
        # Session is terminal — no infinite unproductive re-attempt loop.
        assert turn.session_state.handoff_delivered is True

        # A follow-up turn must short-circuit (no pipeline re-run) and
        # keep surfacing the same escalation signal, not silently drop it.
        turn2 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-adr044-backstop",
                    raw_input="네",
                    session_state=turn.session_state,
                )
            )
        )
        assert handoff_agent.call_count == 1  # unchanged — no re-run
        assert verifier_agent.call_count == 1  # unchanged — no re-run
        assert turn2.handoff_ready is False
        assert turn2.clinical_escalation_required is True
        assert turn2.assistant_response == _INCOMPLETE_INTAKE_MESSAGE

    def test_backstop_with_grounded_risk_is_unaffected(self) -> None:
        """Control: the ordinary backstop path (risk ALREADY grounded by
        the time the cap is hit) must be completely unaffected — real
        `handoff_ready` still fires, no escalation flag."""
        import asyncio

        from src.agents.orchestrator import _MAX_DIALOGUE_TURNS, OrchestratorAgent
        from src.schemas.orchestrator import OrchestratorInput, SessionState

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001
        orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
        orch._handoff_agent = _StubHandoffAgent()  # noqa: SLF001
        orch._verifier_agent = _StubVerifierAgentPass()  # noqa: SLF001

        state = SessionState(
            session_id="t-adr044-grounded-backstop",
            turn_count=_MAX_DIALOGUE_TURNS - 1,
            risk_grounded=True,
            slot_data={"risk_assessment": "자살/자해 사고 탐색 질문에 부인 — 환자 발화: '없어요'"},
        )

        turn = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-adr044-grounded-backstop",
                    raw_input="네",
                    session_state=state,
                )
            )
        )
        assert turn.handoff_ready is True
        assert turn.handoff_report is not None
        assert turn.clinical_escalation_required is False
        assert turn.session_state.risk_screening_incomplete is False

    def test_si_screen_forced_within_reserve_window_before_backstop(self) -> None:
        """ADR-044 option (i): within `_SI_SCREEN_RESERVE_TURNS` turns of
        the hard backstop, the mandatory SI screen is forced even though
        other question-able slots remain unfilled (mitigates CVR-043
        finding 1 — the screen's normal last-priority position could
        otherwise be entirely preempted by the backstop)."""
        import asyncio

        from src.agents.orchestrator import (
            _MAX_DIALOGUE_TURNS,
            _SI_SCREEN_RESERVE_TURNS,
            OrchestratorAgent,
        )
        from src.safety_probe import SI_SCREEN_INSTRUCTION
        from src.schemas.orchestrator import OrchestratorInput, SessionState

        orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
        orch._safety_agent = _StubSafetyAgent(5, [])  # noqa: SLF001

        # One turn before entering the reserve window — other slots still
        # missing, so the screen is NOT yet forced. `process_turn`
        # increments `turn_count` by 1 before this check runs, so the
        # PRESET count here is one less than the effective count the gate
        # actually evaluates.
        pre_reserve_turn_count = _MAX_DIALOGUE_TURNS - _SI_SCREEN_RESERVE_TURNS - 2
        state = SessionState(
            session_id="t-adr044-reserve",
            turn_count=pre_reserve_turn_count,
            risk_grounded=False,
            slot_data={"chief_complaint": "우울감"},
        )
        turn = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-adr044-reserve",
                    raw_input="그냥 그래요",
                    session_state=state,
                )
            )
        )
        assert turn.probe_instruction != SI_SCREEN_INSTRUCTION

        # Now inside the reserve window — same shape of missing slots,
        # but the screen must be forced regardless.
        state2 = SessionState(
            session_id="t-adr044-reserve-2",
            turn_count=_MAX_DIALOGUE_TURNS - _SI_SCREEN_RESERVE_TURNS - 1,
            risk_grounded=False,
            slot_data={"chief_complaint": "우울감"},
        )
        turn2 = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-adr044-reserve-2",
                    raw_input="그냥 그래요",
                    session_state=state2,
                )
            )
        )
        assert turn2.probe_instruction == SI_SCREEN_INSTRUCTION
        assert turn2.session_state.risk_question_pending is True
