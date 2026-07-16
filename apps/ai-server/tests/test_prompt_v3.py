"""PLAN-2026-W28 C1: prompt architecture v3 offline validation.

Covers the 5 newly redesigned prompts (`docs/ai/prompts/prompt_redesign_v3.md`):
  - safety_classifier v2   (ISS-046/048/050, v1 핵심 규칙 7개 존치)
  - dialogue v2             (절대 규칙 8→6, Safety 섹션 5→1줄, P12 dedup)
  - clinical_slot v3        (hold — REV-002 #3: risk_assessment 상호참조 없음)
  - handoff_generator v2    (ADR-007 ctrs_level 제거, P7 placeholder, P10 dedup)
  - sentiment_analyzer v2   (session 모드 삭제, turn_index 예시 제거, P7)

Design-doc §4.1 offline assertions:
  1. placeholder-only examples (no realistic clinical values / echo risk)
  2. required output schema keys documented
  3. absolute-rule key phrases present
  4. char/line budget ceilings, measured with len()/splitlines() (not wc -c)
  5. sentiment session-mode dead examples absent
  6. ISS-050 phrase present in safety_classifier
  7. safety v1 핵심 규칙 (①②③④⑦ verbatim, ⑤⑥ merged) survive
  8. handoff evidence-citation reminder declared once, not repeated in §3/§5/§7

v1/v2 files are never edited or deleted (rollback policy) — only asserted to
still exist on disk.

PLAN-2026-W28-B / ADR-010 (2026-07-07, ISS-049 resolved): safety_classifier
v3 layered on top of v2 above — passive SI (수동적 자살사고) now escalates to
immediate high/CTRS 2 instead of routing through CTRS 3 → Safety Probe
(supersedes ADR-006). The agent pin moves v2 → v3; v2's static-content tests
above stay green (the v2 file itself is unmodified, kept for rollback).
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.clinical_slot import ALL_SLOT_KEYS, ClinicalSlotAgent
from src.agents.clinical_slot import PROMPT_VERSION as CLINICAL_SLOT_VERSION
from src.agents.dialogue import PROMPT_VERSION as DIALOGUE_VERSION
from src.agents.dialogue import DialogueAgent
from src.agents.handoff_generator import _PROMPT_VERSION as HANDOFF_VERSION
from src.agents.handoff_generator import HandoffGeneratorAgent
from src.agents.safety_classifier import PROMPT_VERSION as SAFETY_VERSION
from src.agents.safety_classifier import SafetyClassifierAgent
from src.agents.sentiment_analyzer import PROMPT_VERSION as SENTIMENT_VERSION
from src.agents.sentiment_analyzer import SentimentAnalyzerAgent
from src.schemas.clinical_slot import ClinicalSlotInput
from src.schemas.dialogue import DialogueInput
from src.schemas.handoff import HandoffInput
from src.schemas.safety import SafetyInput
from src.schemas.sentiment import SentimentUtteranceInput

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "ai" / "prompts"


def _read(agent: str, version: str) -> str:
    return (_PROMPTS_DIR / agent / f"{version}.system.md").read_text(encoding="utf-8")


SAFETY_V2 = _read("safety_classifier", "v2")
SAFETY_V3 = _read("safety_classifier", "v3")
DIALOGUE_V2 = _read("dialogue", "v2")
# PLAN-2026-W28-Q W2: dialogue v3 redesign (autonomous turn-0 greeting +
# question-induction continuity phrasing) — superseded by v4 below (v3 file
# kept, rollback policy).
DIALOGUE_V3 = _read("dialogue", "v3")
# BUG-030 / ADR-028: dialogue v4 — empathy-phrase repetition fix (example
# menu -> principle-level natural generation). The ONE licensed prompt
# change this mission; v3 -> v4 (v3 file kept, rollback policy).
DIALOGUE_V4 = _read("dialogue", "v4")
CLINICAL_SLOT_V2 = _read("clinical_slot", "v2")
CLINICAL_SLOT_V3 = _read("clinical_slot", "v3")
HANDOFF_V2 = _read("handoff_generator", "v2")
SENTIMENT_V2 = _read("sentiment_analyzer", "v2")

_ALL_NEW_FILES = {
    "safety_classifier/v2": SAFETY_V2,
    "safety_classifier/v3": SAFETY_V3,
    "dialogue/v2": DIALOGUE_V2,
    "dialogue/v3": DIALOGUE_V3,
    "dialogue/v4": DIALOGUE_V4,
    "clinical_slot/v3": CLINICAL_SLOT_V3,
    "handoff_generator/v2": HANDOFF_V2,
    "sentiment_analyzer/v2": SENTIMENT_V2,
}

# DR-001/ISS-027 echo-risk strings: real-looking clinical values that must
# never appear as "examples" (design doc §4.1 #1, §2.4 P7 table).
_KNOWN_BAD_STRINGS = [
    "서울대병원",
    "Escitalopram",
    "F33.1",
    "요즘 죽고 싶다는 생각이",
    "PHQ-9 | 18",
    "GAD-7 | 12",
    "3-4시간",
    "5-6시간",
    "18점",
    "12점",
    "요즘 계속 불안하고 잠을 못 자요",
]

_ICD_CODE_PATTERN = re.compile(r"F\d{2}")


class TestNoRealisticExampleValues:
    """design doc §4.1 #1 — placeholder-only, applied to all 5 new files."""

    @pytest.mark.parametrize("name", list(_ALL_NEW_FILES))
    def test_no_known_bad_strings(self, name: str) -> None:
        content = _ALL_NEW_FILES[name]
        for bad in _KNOWN_BAD_STRINGS:
            assert bad not in content, f"{name} contains echo-risk string: {bad!r}"

    @pytest.mark.parametrize("name", list(_ALL_NEW_FILES))
    def test_no_icd_code_pattern(self, name: str) -> None:
        content = _ALL_NEW_FILES[name]
        assert not _ICD_CODE_PATTERN.search(content), (
            f"{name} contains an ICD-code-like pattern (F\\d{{2}})"
        )


class TestSafetyClassifierV2File:
    def test_v1_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "safety_classifier" / "v1.system.md").exists()

    def test_output_schema_keys_documented(self) -> None:
        for key in ["risk_level", "categories", "flagged_phrases", "confidence", "reason_summary"]:
            assert key in SAFETY_V2, f"missing output key: {key}"

    def test_absolute_rules_present(self) -> None:
        for phrase in [
            "진단명을 출력하지 않는다",
            "환자 대면 응답을 생성하지 않는다",
            "지정된 5개 필드 외의 필드를 출력하지 않는다",
            "관용구",  # ISS-046
        ]:
            assert phrase in SAFETY_V2, f"missing absolute rule text: {phrase!r}"

    def test_adr006_passive_si_routing_unchanged(self) -> None:
        assert "ADR-006" in SAFETY_V2
        assert "CTRS 3" in SAFETY_V2
        assert "CTRS 2로 임의 상향하지 않는다" in SAFETY_V2

    def test_iss050_consistency_rule_present(self) -> None:
        """design doc §4.1 #6."""
        assert "ISS-050" in SAFETY_V2
        assert "재상향 금지" in SAFETY_V2

    def test_v1_core_rules_survive_verbatim(self) -> None:
        """design doc §4.1 #7 — ①②③④⑦ key phrases must survive."""
        for phrase in ["문맥", "부정", "시제 확인", "상담사", "상향 분류"]:
            assert phrase in SAFETY_V2, f"v1 핵심 규칙 phrase missing: {phrase!r}"

    def test_merged_rule_56_intent_survives(self) -> None:
        """⑤⑥ merged row must keep the "no explicit SI intent" conclusion."""
        assert "명시적 자살/자해 의도가 아니면" in SAFETY_V2

    def test_line_budget(self) -> None:
        assert len(SAFETY_V2.splitlines()) <= 60

    def test_char_budget_documented_deviation(self) -> None:
        """Design-doc target (prompt_redesign_v3.md §2.1, "hold"): <=1900 chars.

        Actual content — 5 absolute rules + 7 verbatim v1 core rules + a
        7-row calibration table + ISS-048/050 additions — cannot fit under
        1900 chars without cutting a load-bearing rule. Per developer brief
        (PLAN-2026-W28 C1) this overshoot is intentional and documented, not
        a silently-trimmed rule; critic's non-blocking observation
        (discussion.md REV-002 status update) anticipated exactly this and
        asked QA to escalate rather than accept a cut rule. Ceiling below is
        the actual measured size with modest headroom, not the original
        1900-char aspiration — it still guards against unbounded growth.
        """
        assert len(SAFETY_V2) <= 2600


class TestSafetyClassifierV3File:
    """PLAN-2026-W28-B / ADR-010 (2026-07-07): ISS-049 resolved — passive SI
    (수동적 자살사고) escalates to immediate high/CTRS 2, no longer routed
    through CTRS 3 → Safety Probe. v2 stays on disk and its static-content
    tests above stay green unmodified; this class covers the new v3 file.

    v3 = rolled-back candidate (ADR-012, EXP-003 SM-04 regression); file kept
    for the v4 iteration.
    """

    def test_v1_and_v2_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "safety_classifier" / "v1.system.md").exists()
        assert (_PROMPTS_DIR / "safety_classifier" / "v2.system.md").exists()

    def test_output_schema_keys_documented(self) -> None:
        for key in ["risk_level", "categories", "flagged_phrases", "confidence", "reason_summary"]:
            assert key in SAFETY_V3, f"missing output key: {key}"

    def test_absolute_rules_present(self) -> None:
        for phrase in [
            "진단명을 출력하지 않는다",
            "환자 대면 응답을 생성하지 않는다",
            "지정된 5개 필드 외의 필드를 출력하지 않는다",
            "관용구",  # ISS-046, unchanged
        ]:
            assert phrase in SAFETY_V3, f"missing absolute rule text: {phrase!r}"

    def test_adr010_passive_si_immediate_ctrs2(self) -> None:
        """design brief item 1 — passive SI escalates to high/CTRS 2, no probe."""
        assert "ADR-010" in SAFETY_V3
        assert "CTRS 2" in SAFETY_V3
        assert "즉시" in SAFETY_V3
        assert "Safety Probe를 경유하지 않는다" in SAFETY_V3

    def test_adr006_provisional_routing_removed(self) -> None:
        """The old CTRS-3-floor-only routing text for passive SI must be gone
        (superseded, not merely appended alongside)."""
        assert "CTRS 2로 임의 상향하지 않는다" not in SAFETY_V3

    def test_calibration_table_passive_si_rows_floor_ctrs2(self) -> None:
        """간접 표현 CTRS 하한표: passive-SI rows now floor at CTRS 2, not 3."""
        assert '"살고 싶지 않다", "사라지고 싶다", "죽고 싶다" | **최소 2단계' in SAFETY_V3
        assert '"내가 없으면 다 편할 텐데", "사는 게 의미가 없다" | **최소 2단계' in SAFETY_V3
        # No row for this expression class may still claim a level-3 floor.
        assert '살고 싶지 않다", "사라지고 싶다", "죽고 싶다" | 최소 3단계' not in SAFETY_V3
        assert '내가 없으면 다 편할 텐데", "사는 게 의미가 없다" | 최소 3단계' not in SAFETY_V3

    def test_self_harm_urge_without_si_keeps_probe_scope(self) -> None:
        """ADR-010 scope carve-out (c): SM-04-class self-harm urge without SI
        keeps CTRS 3 → Safety Probe — the passive-SI class alone leaves the
        probe trigger set."""
        assert "CTRS 3 → Safety Probe 경로를 유지한다" in SAFETY_V3

    def test_negation_rule_present(self) -> None:
        """design brief item 1 — SM-02 negation rule (rule 7) preserved verbatim."""
        assert "죽고 싶다거나 그런 생각은 없어요" in SAFETY_V3
        assert "부정 문맥 확인" in SAFETY_V3

    def test_idiom_rule_present(self) -> None:
        """design brief item 1 — SM-07a panic-idiom rule (rule 4, ISS-046) preserved verbatim."""
        assert "정말 죽는 줄 알았어요" in SAFETY_V3
        assert "관용구/회고 우선 판단" in SAFETY_V3

    def test_iss050_consistency_rule_present(self) -> None:
        assert "ISS-050" in SAFETY_V3
        assert "재상향 금지" in SAFETY_V3

    def test_v1_core_rules_survive_verbatim(self) -> None:
        for phrase in ["문맥", "부정", "시제 확인", "상담사", "상향 분류"]:
            assert phrase in SAFETY_V3, f"v1 핵심 규칙 phrase missing: {phrase!r}"

    def test_merged_rule_56_intent_survives(self) -> None:
        assert "명시적 자살/자해 의도가 아니면" in SAFETY_V3

    def test_line_budget(self) -> None:
        """Measured 2026-07-07: 61 lines (v2 ceiling was 60). The new rule 5
        (ADR-010) plus its two calibration-table row annotations added
        substantive, load-bearing content — the deviation is documented, not
        a silent overshoot, mirroring the v2 ADR-008 precedent below.
        """
        assert len(SAFETY_V3.splitlines()) <= 62

    def test_char_budget_documented_deviation(self) -> None:
        """Measured 2026-07-07: 3060 chars (v2 ceiling was 2600). Content
        added: rule 5 rewritten for ADR-010 (still 1 rule, replacing the old
        ADR-006 rule 5 verbatim-for-verbatim), 2 calibration-table rows
        re-annotated, and a 2-line header changelog note. No rule was cut —
        all 5 absolute rules + 7 judgment principles + 8 calibration rows
        survive (12 rules total, same count as v2). Ceiling set with modest
        headroom over the measured size, same discipline as v2's ADR-008
        acceptance of a documented overshoot.
        """
        assert len(SAFETY_V3) <= 3150


class TestDialogueV2File:
    def test_v1_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "dialogue" / "v1.system.md").exists()

    def test_output_schema_key_documented(self) -> None:
        assert "assistant_response" in DIALOGUE_V2

    def test_absolute_rules_present(self) -> None:
        for phrase in [
            "진단 확정 금지",
            "약물/치료 권유 금지",
            "근거 없는 안심 금지",
            "환자 감정 부정 금지",
            "반말 금지",
        ]:
            assert phrase in DIALOGUE_V2, f"missing absolute rule text: {phrase!r}"

    def test_safety_dedup_p12(self) -> None:
        """Static prompt no longer hardcodes runtime-injected safety/slot content."""
        assert "Safety 지시" in DIALOGUE_V2
        assert "risk_level이 medium 이상" not in DIALOGUE_V2  # old v1 hardcoded branch

    def test_char_budget(self) -> None:
        assert len(DIALOGUE_V2) <= 1500


class TestDialogueV3File:
    """PLAN-2026-W28-Q W2: dialogue v3 redesign — the pinned prompt as of
    this mission. v2's clinical-dialogue core is preserved (evolution, not a
    rewrite); v3 adds autonomous turn-0 greeting + continuity phrasing."""

    def test_v2_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "dialogue" / "v2.system.md").exists()

    def test_output_schema_key_documented(self) -> None:
        assert "assistant_response" in DIALOGUE_V3

    def test_absolute_rules_present(self) -> None:
        for phrase in [
            "진단 확정 금지",
            "약물/치료 권유 금지",
            "근거 없는 안심 금지",
            "환자 감정 부정 금지",
            "반말 금지",
        ]:
            assert phrase in DIALOGUE_V3, f"missing absolute rule text: {phrase!r}"

    def test_safety_dedup_p12(self) -> None:
        """v2's dedup discipline is preserved unchanged."""
        assert "Safety 지시" in DIALOGUE_V3
        assert "risk_level이 medium 이상" not in DIALOGUE_V3  # old v1 hardcoded branch

    def test_opening_turn_section_present(self) -> None:
        """v3 addition (a): autonomous turn-0 greeting is now documented."""
        assert "세션 시작 인사" in DIALOGUE_V3
        assert "슬롯 문진" in DIALOGUE_V3  # "no premature clinical/slot content" rule

    def test_continuity_phrasing_section_present(self) -> None:
        """v3 addition (b): question-induction continuity phrasing."""
        assert "연속성" in DIALOGUE_V3

    def test_no_raw_risk_narration_licensed(self) -> None:
        """AVC-02: the greeting may reference the FACT of a prior session but
        never raw risk narration — the static prompt says so explicitly."""
        assert "위험" not in DIALOGUE_V3 or "추측하거나" in DIALOGUE_V3

    def test_line_budget(self) -> None:
        assert len(DIALOGUE_V2.splitlines()) <= 50


class TestDialogueV4File:
    """BUG-030 / ADR-028 (`_archive/plans/fix_proposal_bug030.md`): dialogue v4 —
    empathy-phrase repetition fix. Rule 2's 3 canned example phrases are
    removed and replaced with a principle-level natural-generation
    instruction; every other v3 structural constraint is carried forward
    verbatim (locked in by re-running v3's own assertions against v4)."""

    def test_v3_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "dialogue" / "v3.system.md").exists()

    def test_output_schema_key_documented(self) -> None:
        assert "assistant_response" in DIALOGUE_V4

    def test_absolute_rules_present(self) -> None:
        for phrase in [
            "진단 확정 금지",
            "약물/치료 권유 금지",
            "근거 없는 안심 금지",
            "환자 감정 부정 금지",
            "반말 금지",
        ]:
            assert phrase in DIALOGUE_V4, f"missing absolute rule text: {phrase!r}"

    def test_safety_dedup_p12(self) -> None:
        """v2/v3's dedup discipline is preserved unchanged (critic condition 5)."""
        assert "Safety 지시" in DIALOGUE_V4
        assert "risk_level이 medium 이상" not in DIALOGUE_V4  # old v1 hardcoded branch

    def test_opening_turn_section_present(self) -> None:
        """v3 addition (a), carried forward unchanged: autonomous turn-0 greeting."""
        assert "세션 시작 인사" in DIALOGUE_V4
        assert "슬롯 문진" in DIALOGUE_V4  # "no premature clinical/slot content" rule

    def test_continuity_phrasing_section_present(self) -> None:
        """v3 addition (b), carried forward unchanged: continuity phrasing."""
        assert "연속성" in DIALOGUE_V4

    def test_no_raw_risk_narration_licensed(self) -> None:
        """AVC-02, carried forward unchanged: fact-of-prior-session only,
        never raw risk narration."""
        assert "위험" not in DIALOGUE_V4 or "추측하거나" in DIALOGUE_V4

    def test_no_canned_empathy_examples(self) -> None:
        """BUG-030 fix intent, at the prompt-file level: none of v3's 3
        canonical example phrases (the specific echo-risk targets) survive
        into v4."""
        for phrase in [
            "많이 힘드셨겠어요.",
            "그런 상황이라면 정말 지치셨을 것 같아요.",
            "이야기해 주셔서 감사합니다.",
        ]:
            assert phrase not in DIALOGUE_V4, f"canned empathy example survives: {phrase!r}"

    def test_principle_level_empathy_instruction_present(self) -> None:
        """BUG-030 fix intent: natural generation, not menu selection."""
        assert "그때그때 새로 표현" in DIALOGUE_V4

    def test_char_budget(self) -> None:
        """Measured 2026-07-12: 3320 chars (v3 was 2513) — growth is the new
        v4 changelog note documenting the BUG-030 fix rationale (rule 2's
        own content is shorter than v3's 3-phrase list, per the fix
        proposal). Ceiling set with modest headroom over the measured size —
        fixes (c-viii)'s v3-class copy-paste bug (asserted DIALOGUE_V2)
        rather than propagating it forward.
        """
        assert len(DIALOGUE_V4) <= 3600

    def test_line_budget(self) -> None:
        """Measured 2026-07-12: 95 lines (v3 was 79). Same rationale as
        test_char_budget above; asserted against DIALOGUE_V4 itself.
        """
        assert len(DIALOGUE_V4.splitlines()) <= 105


# Key anti-fabrication phrases that must survive verbatim from v2 into v3.
_CLINICAL_SLOT_V2_RULES = [
    "묻고 답하지 않은 슬롯은 반드시 null",
    "예시/템플릿 문구를 출력하지 않는다",
    "추론 금지",
    "말하지 않았으니 없을 것이다",
    "risk_assessment는 절대 추론하지 않는다",
    "중대한 임상 기록 위조",
    "다른 주제에 대한 부정 응답을 여러 슬롯에 확대 적용하지 않는다",
]


class TestClinicalSlotV3File:
    def test_v1_and_v2_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "clinical_slot" / "v1.system.md").exists()
        assert (_PROMPTS_DIR / "clinical_slot" / "v2.system.md").exists()

    def test_v3_exists(self) -> None:
        assert (_PROMPTS_DIR / "clinical_slot" / "v3.system.md").exists()

    def test_all_12_keys_present(self) -> None:
        for key in ALL_SLOT_KEYS:
            assert key in CLINICAL_SLOT_V3, f"missing slot key: {key}"

    def test_v2_anti_fabrication_rules_survive_in_v3(self) -> None:
        """design doc §4.1 (e) — every v2 anti-fabrication rule survives verbatim."""
        for rule in _CLINICAL_SLOT_V2_RULES:
            assert rule in CLINICAL_SLOT_V2, f"test fixture stale: {rule!r} missing from v2 itself"
            assert rule in CLINICAL_SLOT_V3, f"v3 dropped a v2 anti-fabrication rule: {rule!r}"

    def test_no_unenforceable_safety_cross_reference(self) -> None:
        """REV-002 #3 — must NOT instruct the model to reconcile against
        SafetyClassifier output it never receives (ClinicalSlotInput has no
        safety_result field)."""
        assert "SafetyClassifier의 risk_level과" not in CLINICAL_SLOT_V3
        assert "상충되지 않아야 한다" not in CLINICAL_SLOT_V3

    def test_no_legacy_alias_keys_taught(self) -> None:
        for alias in ["psychosocial_context", "risk_factors", "protective_factors"]:
            assert alias not in CLINICAL_SLOT_V3, f"v3 must not teach legacy alias: {alias!r}"

    def test_self_check_added(self) -> None:
        assert "자체 점검" in CLINICAL_SLOT_V3

    def test_char_budget(self) -> None:
        assert len(CLINICAL_SLOT_V3) <= 3300

    def test_line_budget(self) -> None:
        assert len(CLINICAL_SLOT_V3.splitlines()) <= 96


_H2_HEADERS = [
    "## 섹션 1. 환자 기본 정보",
    "## 섹션 2. 평가 일시 및 환경",
    "## 섹션 3. 주호소 및 현병력",
    "## 섹션 4. 주요 증상",
    "## 섹션 5. CTRS 기반 위험도 평가",
    "## 섹션 6. 구조화 척도 결과",
    "## 섹션 7. 과거 병력 및 현재 약물",
    "## 섹션 8. 업로드 문서 요약",
    "## 섹션 9. 종단적 상태 변화",
    "## 섹션 10. 추가 정보 필요 사항",
    "## 섹션 11. 추천 진료과 및 사유",
    "## 섹션 12. 근거 레지스트리",
]


class TestHandoffGeneratorV2File:
    def test_v1_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "handoff_generator" / "v1.system.md").exists()

    def test_12_h2_headers_present(self) -> None:
        for h in _H2_HEADERS:
            assert h in HANDOFF_V2, f"missing H2 header: {h!r}"

    def test_evidence_id_convention_present(self) -> None:
        assert "[ev_{source_type}_{3자리 순번}]" in HANDOFF_V2

    def test_no_json_output_instruction(self) -> None:
        """This agent outputs raw markdown; no JSON contract instruction."""
        assert "JSON 출력에 포함" not in HANDOFF_V2
        assert "출력 시 ctrs_level 포함" not in HANDOFF_V2

    def test_no_ctrs_level_output_instruction(self) -> None:
        """ADR-007 option A — dead ctrs_level instruction removed."""
        assert "## 출력 시 ctrs_level 포함" not in HANDOFF_V2
        assert "정수 1-5)을 JSON 출력에 포함" not in HANDOFF_V2

    def test_evidence_citation_removed_from_individual_sections(self) -> None:
        """design doc §4.1 #8 — old §3/§5/§7 reminders gone."""
        assert "모든 기술에 evidence citation을 첨부합니다" not in HANDOFF_V2
        assert "핵심 근거 기술 + evidence citation" not in HANDOFF_V2
        assert "- evidence citation 첨부" not in HANDOFF_V2

    def test_evidence_citation_declared_once_centrally(self) -> None:
        """design doc §4.1 #8 — single central declaration in 핵심 원칙."""
        assert "모든 임상 서술에는 예외 없이 evidence citation을 첨부한다" in HANDOFF_V2

    def test_absolute_rules_present(self) -> None:
        for phrase in [
            "진단 확정 표현 금지",
            "치료 지시 금지",
            "Evidence citation 없는 임상 주장 금지",
            "PHQ-9, GAD-7 점수를 직접 계산하지 않는다",
            "섹션 10(추가 정보 필요 사항",
            "섹션 12(근거 레지스트리)를 생략하지 않는다",
        ]:
            assert phrase in HANDOFF_V2, f"missing absolute rule text: {phrase!r}"

    def test_ctrs_action_table_unchanged(self) -> None:
        """§11 CTRS→조치 graduated wording preserved (ADR-006 consistent)."""
        assert "즉시 응급 의료 연결 (119/112)" in HANDOFF_V2
        assert "정신건강의학과 상담 강력 권고" in HANDOFF_V2

    def test_char_budget(self) -> None:
        assert len(HANDOFF_V2) <= 9200

    def test_line_budget(self) -> None:
        assert len(HANDOFF_V2.splitlines()) <= 245


class TestSentimentAnalyzerV2File:
    def test_v1_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "sentiment_analyzer" / "v1.system.md").exists()

    def test_output_schema_keys_documented(self) -> None:
        for key in ["emotions", "polarity", "arousal", "evidence_phrase", "risk_signal"]:
            assert key in SENTIMENT_V2, f"missing output key: {key}"

    def test_turn_index_example_field_removed(self) -> None:
        """turn_index is code-overwritten (inp.turn_index), never model-supplied."""
        assert '"turn_index":' not in SENTIMENT_V2

    def test_session_mode_dead_examples_removed(self) -> None:
        """design doc §4.1 #5 — session-mode section (never LLM-called) gone."""
        for field in [
            "dominant_emotions",
            "emotion_distribution",
            "polarity_trajectory",
            "repeated_patterns",
            "signal_strength",
            "session_id",
        ]:
            assert field not in SENTIMENT_V2, f"dead session-mode example survives: {field!r}"

    def test_evidence_phrase_placeholder(self) -> None:
        assert "<판정 근거가 된 환자 발화 인용>" in SENTIMENT_V2

    def test_absolute_rules_present(self) -> None:
        for phrase in [
            "진단명 사용 금지",
            "치료 권고 금지",
            "PHQ-9/GAD-7 점수를 직접 계산하지 않는다",
        ]:
            assert phrase in SENTIMENT_V2, f"missing absolute rule text: {phrase!r}"

    def test_char_budget(self) -> None:
        assert len(SENTIMENT_V2) <= 2800

    def test_line_budget(self) -> None:
        assert len(SENTIMENT_V2.splitlines()) <= 80


# ── Agent runtime: pins point at the new versions and report them ──────────


def _wire_adapter(agent: object, resp_content: str) -> AsyncMock:
    router = MagicMock()
    agent._router = router  # type: ignore[attr-defined]
    resp = MagicMock()
    resp.content = resp_content
    resp.model = "test-model"
    resp.latency_ms = 1.0
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    router.get_adapter.return_value = adapter
    router.record_success = MagicMock()
    return adapter


class TestAgentPinsAndRuntimeVersion:
    def test_safety_classifier_pin(self) -> None:
        """ADR-012: rolled back v3 -> v2 after EXP-003's SM-04 probe
        regression (ADR-010's policy stands; the v3 implementation attempt
        does not, pending a v4 iteration)."""
        assert SAFETY_VERSION == "v2"

    def test_dialogue_pin(self) -> None:
        """BUG-030 / ADR-028: dialogue v4 — empathy-phrase repetition fix
        (example menu -> principle-level natural generation); v3 -> v4."""
        assert DIALOGUE_VERSION == "v4"

    def test_clinical_slot_pin(self) -> None:
        assert CLINICAL_SLOT_VERSION == "v3"

    def test_handoff_generator_pin(self) -> None:
        assert HANDOFF_VERSION == "v2"

    def test_sentiment_analyzer_pin(self) -> None:
        assert SENTIMENT_VERSION == "v2"

    @pytest.mark.asyncio
    async def test_safety_classifier_loads_and_reports_v2(self) -> None:
        """ADR-012: agent requests and reports v2 again (rollback from v3)."""
        agent = SafetyClassifierAgent.__new__(SafetyClassifierAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "안전 분류 프롬프트"
        _wire_adapter(
            agent,
            '{"risk_level": "none", "categories": [], "flagged_phrases": [], '
            '"confidence": 0.9, "reason_summary": "ok"}',
        )

        out = await agent.run(SafetyInput(session_id="t", user_message="괜찮아요"))

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "safety_classifier", "v2"
        )
        assert out.prompt_version == "v2"

    @pytest.mark.asyncio
    async def test_dialogue_loads_and_reports_v4(self) -> None:
        agent = DialogueAgent.__new__(DialogueAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "대화 프롬프트"
        _wire_adapter(agent, '{"assistant_response": "안녕하세요"}')

        out = await agent.run(DialogueInput(session_id="t", user_message="안녕하세요"))

        agent._prompt_loader.load_system_prompt.assert_called_once_with("dialogue", "v4")
        assert out.prompt_version == "v4"

    @pytest.mark.asyncio
    async def test_clinical_slot_loads_and_reports_v3(self) -> None:
        agent = ClinicalSlotAgent.__new__(ClinicalSlotAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "슬롯 추출 프롬프트"
        _wire_adapter(agent, "{}")

        out = await agent.run(ClinicalSlotInput(
            session_id="t",
            conversation_history=[{"role": "user", "content": "hi"}],
        ))

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "clinical_slot", "v3"
        )
        assert out.prompt_version == "v3"

    @pytest.mark.asyncio
    async def test_handoff_generator_loads_and_reports_v2(self) -> None:
        agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "인계 보고서 프롬프트"
        _wire_adapter(agent, "## 섹션 1. 환자 기본 정보\n내용")

        out = await agent.run(HandoffInput(session_id="t"))

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "handoff_generator", "v2"
        )
        assert out.prompt_version == "v2"

    @pytest.mark.asyncio
    async def test_sentiment_analyzer_loads_and_reports_v2(self) -> None:
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "감정 분석 프롬프트"
        _wire_adapter(
            agent,
            '{"emotions": [{"label": "neutral", "intensity": 0.5}], "polarity": 0.0, '
            '"arousal": "medium", "evidence_phrase": "그렇군요", "risk_signal": false}',
        )

        out = await agent.run(SentimentUtteranceInput(session_id="t", utterance="그렇군요"))

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "sentiment_analyzer", "v2"
        )
        assert out.prompt_version == "v2"
