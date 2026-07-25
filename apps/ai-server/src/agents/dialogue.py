"""DialogueAgent — 정신건강 사전 문진 대화 에이전트.

환자 발화를 받아 공감적 응답을 생성하고, 임상 슬롯을 추출하며,
slot_coverage가 임계값에 도달하면 handoff_ready를 신호합니다.

반복 방지: 이전 턴에서 물어본 슬롯을 추적하여 같은 질문을 반복하지 않습니다.

역할 분리 원칙(코디네이터 아키텍처 지시, 2026-07-25, BUG-083/084 동반):
이 에이전트는 (1) 환자 답변을 슬롯 계층(OrchestratorAgent/ClinicalSlotAgent)에
전달하고 (2) 그 계층이 결정한 다음 미수집 슬롯에 대한 유도 질문만 생성한다.
"기록/다음 타깃 결정" 자체는 슬롯 계층의 책임이며 이 에이전트가 재구현하지
않는다. **환자-facing 표면(assistant_response)에 슬롯 내부 정보(SLOT_KEY
영문 식별자, "슬롯"/"coverage"/"grounding" 등 내부 용어, denied/unknown
같은 내부 상태 라벨)가 노출되는 것은 심각한 오류다** — BUG-084b가 실제로
관측한 증상("risk_assessment, personal_social_history... 슬롯이 있습니다").
모든 슬롯-리스트 프롬프트 주입은 `_topic_label`/`_topic_list`(자연어 라벨)를
거쳐야 하며, raw dict key를 직접 문자열 보간하지 않는다 — 이 파일 내
`_build_retry_hint`/`_build_opening_context`/`_build_slot_context`의 모든
멀티-슬롯 주입 지점이 이 규칙을 따른다(회귀 테스트:
`tests/test_bug084_repeat_content_and_slot_key_leak.py`).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.grounding import infer_literal_target_slot, is_meta_utterance
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.safety_probe import PROBE_STAGES, infer_literal_probe_stage
from src.schemas.common import RiskLevel
from src.schemas.dialogue import DialogueInput, DialogueLLMResponse, DialogueOutput

logger = logging.getLogger(__name__)

# ── 12 Standard Clinical Slots (통일 스키마) ──────────────────────────
# 정신과 차팅 표준에 맞춘 12개 슬롯. 모든 agent가 이 슬롯 체계를 공유한다.

_ESSENTIAL_SLOTS = [
    "chief_complaint",               # 주호소
    "history_of_present_illness",    # 현병력
    "risk_assessment",               # 위험평가
    "mental_status_exam",            # 정신상태검사
    "clinical_assessment",           # 평가/진단적 인상
]

_ALL_SLOTS = [
    "encounter_metadata",            # 01. 진료 기본정보
    "chief_complaint",               # 02. 주호소
    "history_of_present_illness",    # 03. 현병력
    "past_psychiatric_history",      # 04. 정신과 과거력
    "medical_history",               # 05. 신체질환/신경학적 병력
    "personal_social_history",       # 06. 개인사/사회력
    "family_history",                # 07. 가족력
    "substance_use_history",         # 08. 음주·흡연·물질사용
    "mental_status_exam",            # 09. 정신상태검사
    "risk_assessment",               # 10. 위험평가
    "clinical_assessment",           # 11. 평가/진단적 인상
    "treatment_plan",                # 12. 치료계획/치료내용
]

_SLOT_COVERAGE_THRESHOLD = 0.7
_MAX_HISTORY_TURNS = 8

# BUG-030 iter-2 / BUG-035 (2026-07-12, `_archive/plans/fix_design_bug030_iter2.md`,
# ADR-029): unified check-and-retry guard constants.
_MAX_REGENERATION_ATTEMPTS = 2          # design §3 — max 3 LLM calls/turn
_NEAR_DUP_JACCARD_THRESHOLD = 0.5       # rubric_bug030_acceptance.md §1
_NEAR_DUP_NED_THRESHOLD = 0.3           # rubric_bug030_acceptance.md §1
# ADR-029 Decision 2 (REV-032 Issue 1 ∩ CVR-011 Finding 5): bare "겠" removed
# as a standalone marker (false-positive channel — procedural Korean like
# "여쭤보겠습니다" would otherwise score is_empathy=True with zero affective
# content); "-군요" family added (reflective-acknowledgment coverage, so an
# unmarked reflective template like "힘드시군요"/"그러시군요" can't repeat
# undetected — CVR-011 Finding 5's near-dup blind spot).
# CVR-039 finding 5 / PLAN-2026-W30 cluster B #2: "다행" added so a clause
# carrying it registers as `is_empathy` — required for
# `_degrade_empathy_clause`'s REPLACE branch (vs. PREPEND) to fire on a
# `self_referential_relief` violation (see `_banned_self_referential_
# relief_violation` below): without this, `_is_empathy_clause` on the
# leading span would return False and the degrade would only PREPEND a
# pool phrase, leaving the banned "다행이에요"/"다행입니다" text shipped
# verbatim right after it — the opposite of what this fix requires.
_EMPATHY_MARKERS = (
    "것 같아요", "것 같습니다",
    "감사합니다", "이해", "공감",
    "힘드셨", "힘드시", "지치셨", "지치시",
    "어려우셨", "어려우시",
    "군요",
    "다행",
)

# CVR-039 finding 5 (real transcripts, B1/B2/B3): "다행"-root counselor
# self-referential relief content ("다행이에요"/"다행입니다"/"다행이네요"
# etc.) recurred immediately after safety disclosures despite v5's
# prompt-level ban (CVR-038 finding 1's stated distinguishing principle) —
# a prompt-instruction-ignored failure (`experiments/EXP-030/plan.md` §3
# cluster B row), closed here at the lexical-detection layer instead.
# Root-only match: "다행" inherently denotes the counselor's OWN
# relief/fortunate framing (1인칭 내면 감정 진술) regardless of suffix —
# deliberately narrower than a "positive frame" heuristic (no ambiguous
# keyword-combination logic needed), and a disjoint lexical family from
# the allowed "감사"-root patient-directed gratitude example CVR-038
# itself pinned (finding 1's "서로 다른 어근" fix) — so a legitimate
# "감사해요"/"감사합니다" clause never matches this list.
_BANNED_SELF_REFERENTIAL_RELIEF_MARKERS = ("다행",)

# BUG-037 (2026-07-12, `_archive/plans/fix_design_exhaustion_bug037.md`, PLAN-2026-
# W28-U): output-isolation guard constants. `_MIN_OUTPUT_ISOLATION_LEN`
# guards the containment/equality check against coincidental short-string
# collisions (e.g. a trivial 2-3 char slot value, or a short "네"/"아니요"
# patient reply a legitimate response might independently also contain).
# The fallback text is deliberately generic (no slot/clinical content, no
# question) — it must be safe to ship at ANY point in the conversation,
# since it substitutes for whatever the model was actually trying to say.
_MIN_OUTPUT_ISOLATION_LEN = 15
_OUTPUT_ISOLATION_FALLBACK_RESPONSE = (
    "네, 말씀해 주셔서 감사합니다. 이어서 편하게 이야기 나눠 주세요."
)


# Fix 2 — retry-budget-exhaustion safe degrade, Option C (2026-07-12,
# `_archive/plans/fix_design_exhaustion_bug037.md` §3, ADR-030 Decisions 1/2).
# `_leading_clause_boundary` is a module-level function (not a
# `DialogueAgent` method) so it can be shared by `DialogueAgent.
# _extract_leading_clause`/`_splice_point` AND by the degrade-marker-
# clause constant below, which must compute `_OUTPUT_ISOLATION_FALLBACK_
# RESPONSE`'s own leading clause at IMPORT time, before the class exists —
# one function, so the boundary rule can never drift between call sites.
def _leading_clause_boundary(text: str) -> int | None:
    """Index of the earliest '.'/'!' terminal punctuation in `text`, or
    None if the earliest terminal punctuation found is '?' (the response
    opens directly with a question — no leading clause) or no terminal
    punctuation exists at all."""
    positions = [(text.find(c), c) for c in (".", "!", "?")]
    positions = [(p, c) for p, c in positions if p != -1]
    if not positions:
        return None
    end, term_char = min(positions, key=lambda t: t[0])
    return None if term_char == "?" else end


# Deterministic phrase pool for the empathy-clause safe-degrade path. All
# 4 entries are NORMALIZING/thanks-framed (`rubric_bug030_acceptance.md`
# §6 register category) — deliberately register-NEUTRAL (PASSes with ANY
# preceding-turn polarity under §6's own rule), since the degrade path has
# no runtime polarity signal to match register against (DialogueAgent
# never receives `sentiment` — computed downstream in f1.py, after this
# call returns). Each phrase carries the "감사합니다" marker rubric §1
# itself names as a characteristic empathic marker (satisfies the
# semantic empathy test independent of the production `_EMPATHY_MARKERS`
# list — CVR-013 condition 2 / requirement 1(a); see
# `tests/repro/test_fix2_exhaustion_degrade.py::
# TestPoolPhrasesSatisfySemanticEmpathyTest`) and is a DIFFERENT phrase
# family (rubric §1 near-duplicate rule) from every other pool entry and
# from `_OUTPUT_ISOLATION_FALLBACK_RESPONSE`'s own leading clause —
# verified by direct pairwise computation, not eyeballed (same test
# module, `TestPoolPhrasesAreMutuallyDistinctFamilies`).
_EMPATHY_DEGRADE_POOL: tuple[str, ...] = (
    "이렇게 솔직하게 이야기해 주셔서 감사합니다",
    "편하게 마음을 나눠주셔서 감사합니다",
    "그런 마음까지 들려주셔서 감사합니다",
    "오늘 이야기 함께 나눠주셔서 감사합니다",
)


def _fallback_leading_clause() -> str:
    """`_OUTPUT_ISOLATION_FALLBACK_RESPONSE`'s own leading clause,
    computed once at import time via the shared boundary rule — used only
    to build `_DEGRADE_MARKER_CLAUSES` below."""
    stripped = _OUTPUT_ISOLATION_FALLBACK_RESPONSE.strip()
    end = _leading_clause_boundary(stripped)
    return stripped[:end].strip() if end is not None else ""


# REV-034 live finding / ADR-030 Decision 1: the exact, closed set of
# clause strings the SYSTEM ITSELF can ship as a leading clause (never
# organically generated by the model) — the BUG-037 neutral fallback's
# own opener, plus every Fix-2 degrade pool phrase. `run()` excludes any
# clause in this set from the production near-dup guard's
# `session_clauses` population (`_exclude_degrade_marker_clauses`),
# closing the guard-drift/measurement-contamination channel REV-034
# flagged live: a system-inserted clause must never itself trip the
# back-to-back/session-cap check against a LATER, genuinely
# model-generated clause. Exact-string matching only (both sources are
# fixed, closed, enumerable text — not a heuristic).
_DEGRADE_MARKER_CLAUSES: frozenset[str] = frozenset(
    (_fallback_leading_clause(),) + _EMPATHY_DEGRADE_POOL
)

# BUG-030 / ADR-028 (2026-07-12, `_archive/plans/fix_proposal_bug030.md`): v4 —
# empathy-phrase repetition fix. The static prompt's rule-2 example phrases
# and the runtime `_build_slot_context` `alternatives` re-recommendation
# menu are both removed (channels (a)/(b) of the diagnosis); replaced with a
# principle-level "generate natural empathy matched to content/register"
# instruction plus a negative-constraint-only (never re-recommend) runtime
# hint. Every other v3 structural constraint (1-sentence cap, no verbatim
# repetition of the patient's words, no 2-consecutive-turn reuse, opening/
# continuity sections, absolute rules 1-6, output format) is carried
# forward unchanged. `safety_classifier` stays pinned v2, untouched.
# PLAN-2026-W28-Q W2: v3 (dialogue v3 redesign, `apps/ai-server/prompts/dialogue/
# v3.system.md`) — DialogueAgent is now called at turn 0 too (autonomous,
# conditions-aware greeting via session_state["opening_turn"], replacing the
# old hardcoded f-string greeting) plus continuity phrasing for slots
# missing from a prior session (session_state["prior_missing_slots"]). v2's
# clinical-dialogue core is preserved unchanged (evolution, not a rewrite).
# PLAN-2026-W28 C1: v2 (prompt_redesign_v3.md §2.2) — absolute rules 8→6,
# Safety section 5→1 line (P12 dedup vs runtime-injected slot/safety context).
#
# EXP-029 Stage A2 / CVR-038 (cleared-with-conditions, condition applied):
# v5 — addition-only over v4 (v4 body byte-identical), 3 new sections
# targeting CVR-035 findings 1/2/3/5 (위기 인접 발화 처리 우선순위, 질문
# 의도 다양화, 공감 캘리브레이션). CVR-038's one pin condition: the
# 공감 캘리브레이션 section's banned/allowed examples previously shared the
# "다행" root with no stated distinguishing principle — fixed by (a)
# stating the principle explicitly (banned = 상담자 1인칭 내면 감정 진술;
# allowed = 환자 사실-지향 짧은 인정) and (b) swapping the allowed example
# to a different root ("그런 변화가 있었군요") so the two can't be
# pattern-confused regardless of whether the principle is read. Every
# existing red-line (6 절대 규칙, 1문장 공감/1질문, BUG-030 no-literal-menu
# discipline) is unchanged. Live-verified before this pin (see
# tests/test_deploy_contracts.py::TestExp029A2DialogueV5Live) — real
# Upstage Solar Pro3 calls, all 3 scenarios passed.
# STATE-2026-07-21f / PLAN-2026-W30 cluster B #2 (`experiments/EXP-030/
# plan.md` §3): v5.1 — addition-only over v5 (v5 body byte-identical
# except the 공감 캘리브레이션 section, replaced per this pin — see
# `dialogue/v5.1.system.md`'s own changelog note). Closes CVR-039 finding
# 5 (the "다행" root ban recurred in real transcripts despite v5's
# prompt-level instruction): the "다행"-root guidance is now an explicit,
# surface-form-enumerated prohibition instead of only the abstract
# distinguishing principle, AND is now additionally enforced at the code
# layer (`_banned_self_referential_relief_violation`, wired into `run()`'s
# guard loop, degraded via the existing `_degrade_empathy_clause` splice
# on retry-budget exhaustion — no new LLM call). Every other v5 section
# (위기 인접 발화 처리 우선순위, 질문 의도 다양화, 6 절대 규칙, 1문장
# 공감/1질문, BUG-030 no-literal-menu discipline) is unchanged.
#
# BUG-074 (2026-07-25, qa live repro `d2d9ba21`): v5.2 — addition-only over
# v5.1 (v5.1 body byte-identical, see `prompts/dialogue/v5.2.system.md`'s own
# changelog note) — adds exactly one new section, "환자 메타-발화 처리",
# distinguishing a patient's self-disclosure (already covered by "공감
# 캘리브레이션") from a meta-utterance about the conversation/agent itself
# (e.g. "왜 자꾸 물어봐"), which the model previously misattributed as a
# third-party disclosure and empathized with the wrong referent. No code-
# level guard is added for this class this wave (prompt-only fix, per the
# BUG's own routing) — unlike the v5.1 self-referential-relief case, there
# is no cheap deterministic string check for "is this utterance about the
# agent" the way there is for a fixed "다행" root.
#
# BUG-077 (2026-07-25, qa live re-verification `ad0da8c1`) / BUG-074
# residual: v5.3 — addition-only over v5.2 (v5.2 body byte-identical, see
# `prompts/dialogue/v5.3.system.md`'s own changelog note). Two prompt-level
# changes: (1) "환자 메타-발화 처리" widened to recognize INDIRECT
# repetition complaints ("아까도 말했잖아요" 류, not just direct "왜 자꾸
# 물어봐" phrasing) + an explicit scope boundary so the section's
# repeat-acknowledgment opener is never preemptively applied on a plain
# turn that carries no actual meta-utterance (observed over-application,
# `experiments/EXP-032_f1_reverify` t3); (2) "질문 의도 다양화" gains an
# explicit instruction against substituting the assigned target topic with
# a vague catch-all question. Item (1)/(2) are prompt-only (addition,
# existing sections preserved verbatim per this file's own convention).
# BUG-077 item (A)'s PRIMARY mechanism (user directive 2026-07-25: "don't
# force behavior via isolated examples — check whether unnaturalness comes
# FROM the forcing") is state-VISIBILITY, not a hard rule:
# `_build_slot_context`/`_build_asked_topic_history` shows the model an
# explicit filled/denied slot ledger + a literal question-answer history
# (using `src.grounding.infer_literal_target_slot` — the SAME topic-keyword
# definition `OrchestratorAgent`'s BUG-077 attribution fix uses, so "what
# did this text literally ask about" cannot drift between the two call
# sites) so the model can reason its own way out of repeating a generic
# catch-all, instead of being told a rule from outside. `run()`'s guard
# loop (`_resolve_round_robin_target`/`_is_catchall_question`/
# `_count_prior_catchall_turns`/`_force_target_question`) is a SAFETY NET
# only — it never intercepts a session's FIRST catch-all question at all
# (gated on `prior_catchall_turns >= 1`), engaging only if the visibility
# ledger turns out insufficient and the SAME generic-question shape recurs.
#
# BUG-078 CVR-055 #3 follow-up (2026-07-25, qa live re-verification
# `ef4a2b55`, non-blocking part of the same wave as the blocking
# `_advance_safety_probe` code fix — see `agents/orchestrator.py`): v5.4 —
# the v5.2/v5.3 "환자 메타-발화 처리" sections' own worked-example sentences
# ("같은 질문을 반복해서 불편하셨겠어요." / "같은 걸 다시 여쭤서
# 불편하셨겠어요.") were reproduced VERBATIM by the model live, twice, on
# two different turns (BUG-030-lineage prompt-example-anchoring recurrence
# — the "문구 암기 금지" instruction sitting directly next to a single
# copyable sentence did not prevent copying it). Unlike every prior
# version in this file's history, this is NOT addition-only: the two
# example bullets are replaced with an abstract shape/principle
# description that gives the model no single quotable sentence to anchor
# on, mirroring v4's BUG-030 fix for the (unrelated) empathy-calibration
# examples. Every other line of both meta-utterance sections (판별 기준,
# 공감 절감 지시, 금지 예시 안티패턴, 간접 문구 인지, 적용 범위 경계) is
# unchanged — only the two "예시(형태만 참고, 문구 암기 금지)" bullets are
# rewritten to describe the response's SHAPE (short repetition
# acknowledgment, no third-party-referent phrasing, 1 sentence) instead of
# supplying literal text. No other section of v5.3 changes.
#
# BUG-079 / REV-022 §4 (2026-07-25, user directive): v5.5 — the ONLY
# section touched is "공감 캘리브레이션" (v5→v5.1's accumulated per-
# incident additions — weight-proportional-length rule, 4 worked examples,
# an anti-pattern paragraph, an explicit distinguishing-principle
# paragraph — had grown into exactly the "누적 금지어·지침의 협착" REV-022
# flagged). Replaced with a concise 1-2 sentence principle ("짧고 진심
# 어린 인정 한 문장 후 자연스럽게 다음 질문으로; 과장·반복·형식적 공감
# 금지") plus the ONE safety-critical enumerated ban CVR-039/CVR-041 kept
# a live-verified finding for ("다행" root self-referential relief,
# already double-defended at the code layer by `_banned_self_referential_
# relief_violation`). No other content is lost — every other prior bullet
# was pure prompt-level guidance never duplicated by a code guard, and the
# new principle sentence still conveys the core intent (proportional,
# non-repetitive, patient-directed acknowledgment). Every other section
# (역할, 대화 스타일, 위기 인접 발화 처리 우선순위, 질문 의도 다양화, both
# 환자 메타-발화 처리 sections, 세션 시작 인사, Safety 지시 우선 반영,
# 절대 규칙 6개, 출력 형식) is byte-identical to v5.4.

# BUG-085-follow-up (2026-07-25, user-reported live P0, session `04cfe927`):
# v5.6 — two changes, both addition/replacement-only (no other section
# touched). (1) "공감 캘리브레이션" is replaced with an abstract
# utterance-type -> response-shape mapping principle (CVR-057's 6-type
# discriminant table, condensed to principle language -- no literal
# example sentences, per the same BUG-030 anchoring lesson v5.4/v5.5
# already apply) -- the live session showed a FACT-only reply ("술과
# 수면제 복용중이에요") and TWO distinct meta-utterance replies each
# drawing high-intensity distress empathy ("정말 힘드실 것 같아요"),
# which CVR-057 rates `inadequate` against its own discriminant table.
# (2) "환자 메타-발화 처리" widened (principle-level, not a new literal
# keyword list in the prompt -- the corresponding CODE-level gate,
# `src.grounding._META_UTTERANCE_KEYWORDS`/`is_meta_utterance`, is
# widened separately) to cover a THIRD meta-utterance shape this prompt
# never named: complaints about the AGENT's OWN capability/memory
# ("기억 못하시나요?", "너 못하냐고") -- same live session, turns 8/9,
# neither a self/emotion disclosure nor a repetition complaint, and the
# model responded to both as if they were emotional self-disclosure.
PROMPT_VERSION = "v5.6"

# BUG-085-follow-up (session `04cfe927`, probe-topic-mismatch guard):
# stage-name -> question_hint lookup, sourced verbatim from
# `safety_probe.PROBE_STAGES` (never independently invented) -- used by
# `run()`'s exhaustion path to compose a deterministic, stage-bound
# question when the model ignores `probe_instruction` and drifts onto an
# unrelated topic for 2+ regeneration attempts (see `_force_probe_question`
# below).
_PROBE_STAGE_HINTS: dict[str, str] = dict(PROBE_STAGES)

# 직접 질문하지 않는 슬롯 (관찰/자동생성/의료진 영역)
_NO_QUESTION_SLOTS = {
    "encounter_metadata",   # 시스템 자동
    "mental_status_exam",   # 관찰 기반 — 환자에게 질문 안 함
    "clinical_assessment",  # 대화 종료 후 자동 생성
    "treatment_plan",       # 의료진 영역
}

# Per-slot question guides — 대화 중 각 슬롯 수집을 위한 구체적 질문 예시
_SLOT_QUESTION_GUIDE: dict[str, str] = {
    "encounter_metadata":         "(시스템 자동 수집 — 질문 불필요)",
    "chief_complaint":            "오늘 가장 도움받고 싶은 문제나 증상이 무엇인지",
    "history_of_present_illness": "증상이 언제부터 시작되었고 최근 좋아지는지 악화되는지, 일상생활(수면/식사/일/대인관계)에서 가장 영향 받은 부분",  # noqa: E501
    # CVR-056 finding 3: this guide previously packed BOTH self-harm/SI and
    # other-directed-harm into one sentence — when composed verbatim into a
    # single deterministic question (`_force_target_question`, or echoed by
    # the model as a single-turn guide), that produces exactly the
    # compound-question shape CVR-056 flagged live (`question_mark_count:
    # 2`, self-harm and other-directed-harm mixed into one answer with no
    # way to tell which was denied). Narrowed to SI/self-harm only — the
    # single most safety-critical, single-topic screening question; a
    # separate other-directed-harm exploration is out of this fix's scope
    # (not previously asked as its own slot either).
    "risk_assessment":            "안전 확인: 최근 스스로를 해치고 싶거나 죽고 싶다는 생각이 든 적이 있는지 (반드시 한 가지만 물어야 함)",  # noqa: E501
    "substance_use_history":      "최근 술, 수면제, 진정제, 카페인 등 증상에 영향 줄 수 있는 것 사용 여부",  # noqa: E501
    "past_psychiatric_history":   "현재 정신건강의학과 진료나 심리상담 여부, 진단받은 병명이 있는지, 기존 진료기록 확인",  # noqa: E501
    "medical_history":            "진단받은 신체질환이 있는지, 기존 처방 약 외 새로 복용 중인 약이나 변경된 약 여부",  # noqa: E501
    "personal_social_history":    "힘들 때 연락하거나 도움을 요청할 수 있는 사람이 있는지",
    "family_history":             "가족분들 중에 비슷한 어려움을 겪으셨던 분이 계신지",
    "mental_status_exam":         "(관찰 기반: 대화 중 외모, 말투, 기분, 사고과정 관찰하여 기록. 직접 질문 불필요)",  # noqa: E501
    "clinical_assessment":        "(대화 종료 후 수집 정보 종합하여 생성. 직접 질문 불필요)",
    "treatment_plan":             "(의료진 영역. AI는 생성하지 않음. 질문 불필요)",
}

# BUG-084b (2026-07-25, user-reported live P0): short, natural-language
# Korean topic labels for the 12 standard slot keys — used ONLY when a
# LIST of missing/prior/remaining slot identifiers must be injected into
# an LLM-facing prompt/hint (`_build_retry_hint`'s `exact_repeat`/
# `question_repeat` branches, `_build_opening_context`'s prior-session
# continuity line, `_build_slot_context`'s "이후 미수집" line, and this
# turn's own "## 이번 턴: {target}" header). The pre-fix code joined RAW
# English `SLOT_KEY` identifiers (`", ".join(missing)`) directly into
# these strings with no "internal-only, do not echo" instruction — live
# session `94f75e81` shows the model then echoed the raw list verbatim to
# the patient ("risk_assessment, personal_social_history, family_history,
# substance_use_history 중 아직 다루지 않은 슬롯이 있습니다"). Every
# multi-slot-list injection site now renders through `_topic_list` below
# instead of a raw key join, mirroring the discipline `_SLOT_QUESTION_
# GUIDE`'s own natural-language phrasing already applies to the SINGLE
# current-target case. Deliberately SHORT noun-phrase labels (not the
# full `_SLOT_QUESTION_GUIDE` sentence) — these render inside a
# comma-joined list, where a full guide sentence per item would be
# unreadable/unwieldy; the single-target "질문 방향" line keeps using the
# full guide text unchanged, only the list-of-multiple-slots sites change.
_SLOT_TOPIC_LABELS: dict[str, str] = {
    "encounter_metadata":         "기본 정보",
    "chief_complaint":            "오늘 가장 힘든 문제",
    "history_of_present_illness": "증상의 경과",
    "risk_assessment":            "안전 확인",
    "substance_use_history":      "음주·약물 사용 여부",
    "past_psychiatric_history":   "정신과 진료 이력",
    "medical_history":            "신체질환·복용 약",
    "personal_social_history":    "주변 지지체계",
    "family_history":             "가족력",
    "mental_status_exam":         "정신상태 관찰",
    "clinical_assessment":        "종합 평가",
    "treatment_plan":             "치료 계획",
}


def _topic_label(slot: str | None) -> str:
    """Natural-language topic label for a single slot key — falls back to
    the raw key only when genuinely unrecognized (should not happen for
    any of the 12 standard slots), never raising."""
    if not slot:
        return ""
    return _SLOT_TOPIC_LABELS.get(slot, slot)


def _topic_list(slots: list[str]) -> str:
    """Comma-joined natural-language topic list for `slots` — the
    BUG-084b-safe replacement for `", ".join(slots)` (raw key identifiers)
    at every multi-slot prompt-injection site."""
    return ", ".join(_topic_label(s) for s in slots)


class DialogueAgent(BaseAgent):
    """Dialogue agent for psychiatric pre-consultation conversations."""

    def __init__(self, model_router: ModelRouter, prompt_loader: PromptLoader) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return "dialogue"

    async def run(self, inp: AgentInput, **kwargs: Any) -> DialogueOutput:
        """Dialogue Agent — 공감 응답 + 유도 질문 생성만 담당.

        역할 경계:
          - Slot 추출: ClinicalSlotAgent의 역할 (이 Agent가 하지 않음)
          - 위험도 판단: SafetyClassifierAgent의 역할 (이 Agent가 하지 않음)
          - Coverage 계산: f1.py orchestrator의 역할 (이 Agent가 하지 않음)

        이 Agent의 책임:
          - filled_slots(Slot Agent가 갱신)를 읽고 → 미수집 슬롯에 대한 질문 생성
          - safety_result(Safety Agent 결과)를 읽고 → 위험도에 맞는 톤 조절
          - 공감 1문장 + 새 질문 1개 생성
        """
        if not isinstance(inp, DialogueInput):
            raise TypeError(f"Expected DialogueInput, got {type(inp).__name__}")

        started = time.perf_counter()

        # 1. Load system prompt
        prompts_degraded = False
        try:
            system_prompt = self._prompt_loader.load_system_prompt("dialogue", PROMPT_VERSION)
        except FileNotFoundError:
            logger.warning("Dialogue prompt not found, using fallback")
            system_prompt = (
                "당신은 Neuro-Sync 정신건강 사전 문진 AI입니다. "
                "환자의 이야기를 경청하고, 공감적으로 응답합니다. "
                "반드시 한국어로 응답하세요. "
                "JSON으로 응답: {\"assistant_response\": \"응답 텍스트\"}"
            )
            prompts_degraded = True

        # 2. Build slot context (Slot Agent 결과 기반 → 미수집 슬롯 유도 질문)
        slot_context = self._build_slot_context(
            inp.filled_slots, inp.session_state, inp.conversation_history,
        )

        # 3. Safety 결과에 따른 톤 조절 지시
        safety_context = ""
        if inp.safety_result:
            risk = inp.safety_result.get("risk_level", "none")
            if risk in ("medium", "high"):
                safety_context = (
                    "\n\n[Safety 참고: 이전 Safety Agent가 위험 수준을 "
                    f"'{risk}'로 판정했습니다. 공감적이고 안전한 톤으로 응답하세요. "
                    "직접 위기 상담을 하지 말고, 따뜻하게 경청하세요.]"
                )

        # 4. Build messages — PHR history(사전 인지) → slot context(지시)
        #                    → base prompt → safety
        full_system = ""
        # 환자 PHR 요약이 있으면 dialogue system prompt 맨 앞에 삽입해
        # LLM이 대화 시작 전부터 병력·복약을 인지한 상태로 응답하게 한다.
        history_ctx = (inp.patient_history_context or "").strip()
        if history_ctx:
            full_system += history_ctx + "\n\n---\n\n"
        if slot_context:
            full_system += slot_context + "\n\n---\n\n"
        full_system += system_prompt
        if safety_context:
            full_system += safety_context

        messages: list[ChatMessage] = [ChatMessage(role="system", content=full_system)]
        for turn in inp.conversation_history:
            messages.append(ChatMessage(
                role=turn.get("role", "user"),
                content=turn["content"],
            ))
        messages.append(ChatMessage(role="user", content=inp.user_message))

        # 5. Call LLM
        selection = self._router.select_model("dialogue", require_json=True)
        adapter = self._router.get_adapter(selection.adapter_name)
        assert isinstance(adapter, LLMAdapter)

        response_format = None
        if selection.supports_json_schema or selection.supports_json_object:
            response_format = {"type": "json_object"}

        try:
            resp = await adapter.chat_timed(
                messages,
                model=selection.model_id,
                temperature=0.4,
                max_tokens=512,
                response_format=response_format,
            )
            self._router.record_success(selection.adapter_name)
        except Exception as exc:
            logger.error("Dialogue LLM failed: %s", exc)
            self._router.record_failure(selection.adapter_name, exc)

            fallback = self._router.get_fallback(
                "dialogue", selection.adapter_name, str(exc),
            )
            if fallback is None:
                raise

            fb_adapter = self._router.get_adapter(fallback.adapter_name)
            assert isinstance(fb_adapter, LLMAdapter)
            fb_format = (
                {"type": "json_object"}
                if fallback.supports_json_schema or fallback.supports_json_object
                else None
            )
            resp = await fb_adapter.chat_timed(
                messages,
                model=fallback.model_id,
                temperature=0.4,
                max_tokens=512,
                response_format=fb_format,
            )
            self._router.record_success(fallback.adapter_name)

        # 6. Parse response — assistant_response만 추출
        llm_resp = self._parse_response(resp.content)

        # 7. Output-isolation / repetition / near-duplicate / empathy-presence
        # guard. (BUG-030 iter-2, BUG-035, BUG-037,
        # `_archive/plans/fix_design_bug030_iter2.md` §1,
        # `_archive/plans/fix_design_exhaustion_bug037.md` §2, ADR-029,
        # PLAN-2026-W28-U.) Single bounded check-and-retry loop: on each
        # candidate, evaluate output-isolation (clinical-note leak /
        # patient echo), exact-repeat, near-duplicate empathy clause, and
        # empathy-presence-missing on a crisis-adjacent turn, sharing one
        # retry budget across all four.
        #
        # Priority order (highest first): output_isolation > presence_missing
        # > exact_repeat > near_dup. output_isolation sits ABOVE
        # presence_missing (ADR-029 Decision 5 only binds presence_missing's
        # priority over exact_repeat/near_dup, not over a check that didn't
        # exist yet): an isolation violation means the candidate is not a
        # valid patient-facing message AT ALL (raw clinical-note prose or a
        # mechanical echo, not a stylistically-imperfect-but-genuine reply),
        # and is the more severe failure class (CVR-012 F1: "interface-
        # integrity/trust breach... at the single highest-stakes moment of
        # the intake" vs. presence_missing's naturalness/rapport concern).
        # It is checked regardless of crisis_adjacent, since the leak/echo
        # shape does not depend on that turn's risk classification.
        # ADR-030 Decision 1 / REV-034: exclude any clause the SYSTEM
        # itself shipped via a prior fallback/degrade from the guard's own
        # population — see `_DEGRADE_MARKER_CLAUSES`.
        session_clauses = self._exclude_degrade_marker_clauses(
            self._extract_used_empathy_clauses(inp.conversation_history),
        )
        # BUG-048 Finding (b): the same FULL-session, unwindowed, no-dedup
        # discipline as `session_clauses` above, but for the substantive
        # (post-empathy) span — no degrade-marker exclusion needed here
        # (that closed set is empathy-lead-in text only; it never matches a
        # trailing question span).
        session_question_clauses = self._extract_used_trailing_clauses(
            inp.conversation_history
        )
        crisis_adjacent = self._is_crisis_adjacent_turn(inp)

        # BUG-077 item (A): resolve THIS turn's round-robin target the same
        # way `_build_slot_context` does (BUG-056 union of the caller's
        # `filled_slots` with the orchestrator's own `state.slot_data`) —
        # None in opening/probe/summary-mode turns, where no round-robin
        # target applies and the guard below is inert.
        target_slot = self._resolve_round_robin_target(inp)

        # BUG-085-follow-up (session `04cfe927`): the topic THIS turn's
        # rendered probe question is expected to reflect, when
        # `probe_instruction` is active (`target_slot` is None on these
        # turns by design — see `_resolve_round_robin_target`, so the
        # round-robin `target_mismatch`/`catchall_violation` guards are
        # structurally inert here). `probe_instruction`'s own text embeds
        # `PROBE_STAGES[stage_idx]`'s question_hint verbatim
        # (`safety_probe.build_probe_instruction`) — reusing
        # `infer_literal_probe_stage` on that text (the SAME primitive
        # `OrchestratorAgent._advance_safety_probe` uses to validate a
        # PRIOR turn's rendering) recovers the stage name without a new
        # session_state field. None whenever this is not a probe turn, or
        # the probe_instruction text itself doesn't literally name a stage
        # (defensive — should not happen, `build_probe_instruction` always
        # embeds one).
        probe_instruction_text = (inp.session_state or {}).get("probe_instruction")
        expected_probe_stage = (
            infer_literal_probe_stage(str(probe_instruction_text))
            if probe_instruction_text else None
        )

        retry_count = 0
        retry_reasons: list[str] = []
        fall_through = False
        output_isolation_fallback = False
        # Fix 2 (`_archive/plans/fix_design_exhaustion_bug037.md` §3, ADR-030):
        # set only on the retry-budget-exhaustion safe-degrade path.
        exhaustion_degrade: str | None = None
        exhaustion_degrade_phrase: str | None = None
        retry_latency_ms = 0.0
        # BUG-036 telemetry (resolution-recommendation: "Telemetry must
        # record what the guard catches — which sub-rule fired, family,
        # count"). Appended whenever the near-dup CHECK detects a match on
        # an attempt, independent of whether it ends up being the acted-
        # upon `violation` this iteration (isolation/presence/exact_repeat
        # can outrank it) — this is what the sub-check itself observed.
        near_dup_detail: list[dict[str, Any]] = []

        while True:
            prev_responses = self._get_previous_responses(inp.conversation_history)
            is_repeated = (
                llm_resp.assistant_response in prev_responses
                or any(
                    llm_resp.assistant_response == prev
                    for prev in prev_responses
                    if len(prev) >= 80
                )
            )

            candidate_clause = self._extract_leading_clause(llm_resp.assistant_response)
            is_empathy = self._is_empathy_clause(candidate_clause)
            # CVR-041 pin (dialogue v5.1 re-gate): scan the FULL
            # `assistant_response`, not just the leading clause — the
            # prompt's own "다행" ban is stated as an exception-free
            # absolute rule (position/surface-form unspecified), but the
            # leading-clause-only scope left a same-turn SECOND clause
            # (e.g. "...감사해요. 다행이네요. 언제부터...?") completely
            # undetected. CVR-041 confirmed low false-positive risk: the
            # "다행" root never overlaps the allowed "감사"/"~군요" families,
            # so widening the scan does not risk flagging legitimate
            # empathy content. NOTE (honest scope disclosure): the
            # retry-budget-EXHAUSTION degrade path below
            # (`_degrade_empathy_clause`) still only ever splices the
            # LEADING-clause span — a violation caught SOLELY in a
            # trailing clause, on the rare compound event of also
            # exhausting both regeneration retries, would not be removed
            # by the splice itself. This is unchanged, existing degrade
            # scope (not widened this pass, per mission's "keep the
            # degrade path intact") — the widened DETECTION here still
            # forces the normal retry-regenerate path first, which is the
            # primary defense and (per CVR-041) the one this pin actually
            # targets.
            self_ref_relief_violation = self._banned_self_referential_relief_violation(
                llm_resp.assistant_response
            )
            near_dup_reason = (
                self._empathy_repetition_violation(candidate_clause, session_clauses)
                if is_empathy else None
            )
            if near_dup_reason:
                near_dup_detail.append({
                    "kind": "empathy",
                    "reason": near_dup_reason,
                    "family": candidate_clause,
                    "count": self._family_count(candidate_clause, session_clauses),
                })
            # 4연속 verbatim 도입부 반복 (last-resort, independent of
            # `is_empathy`) — see `_leading_prefix_repeat_violation`'s own
            # docstring for the live repro this closes. Deliberately
            # computed unconditionally (not gated on `is_empathy`), since
            # the whole point is to catch a leading clause the marker-based
            # `_is_empathy_clause` heuristic failed to classify.
            leading_prefix_repeat = self._leading_prefix_repeat_violation(
                candidate_clause, session_clauses,
            )
            # BUG-048 Finding (b): the guard above covers ONLY the leading
            # empathy clause — a varying empathy lead-in previously let the
            # SUBSTANTIVE follow-up-question sentence (the span after that
            # lead-in, or the whole response when there is none) repeat
            # byte-identically across non-adjacent turns, undetected (9x in
            # EXP-028c). Same back-to-back/session-cap check
            # (`_empathy_repetition_violation`'s body is generic over any
            # clause + session-clause list, not empathy-specific), applied
            # to the trailing/question span instead.
            question_clause = self._extract_trailing_clause(llm_resp.assistant_response)
            question_dup_reason = self._empathy_repetition_violation(
                question_clause, session_question_clauses
            )
            if question_dup_reason:
                near_dup_detail.append({
                    "kind": "question",
                    "reason": question_dup_reason,
                    "family": question_clause,
                    "count": self._family_count(question_clause, session_question_clauses),
                })
            presence_missing = crisis_adjacent and not is_empathy
            # Coordinator directive (2026-07-25, role-separation principle):
            # checked ABOVE `isolation_reason` — a raw slot-key/internal-
            # term leak is the single most severe interface-integrity
            # breach this guard loop screens for (see `_internal_leak_
            # violation`'s own docstring).
            internal_leak = self._internal_leak_violation(llm_resp.assistant_response)
            isolation_reason = self._output_isolation_violation(
                llm_resp.assistant_response, inp.filled_slots,
                inp.slot_updates_this_turn, inp.user_message,
            )
            # BUG-077 item (A) — SAFETY NET ONLY (user directive 2026-07-25):
            # the PRIMARY mechanism is `_build_slot_context`'s state-
            # visibility ledger (`_build_asked_topic_history` — shows the
            # model its own already-asked topics, including a prior generic
            # catch-all, so it can self-correct without a mechanical rule).
            # This guard exists for when that visibility turns out
            # insufficient in practice: it only engages once a generic
            # catch-all has ALREADY occurred once this session
            # (`prior_catchall_turns >= 1`) — the session's FIRST catch-all
            # question is never intercepted here at all, exactly mirroring
            # the ledger's own framing ("이미 한 번 범용 질문을 썼다면"). A
            # round-robin turn (`target_slot` set) whose rendered question
            # cannot be tied to ANY specific question-able slot topic
            # (`infer_literal_target_slot` returns None) AND repeats a prior
            # catch-all is the live repro's recurring-catch-all shape.
            prior_catchall_turns = (
                DialogueAgent._count_prior_catchall_turns(inp.conversation_history)
                if target_slot is not None else 0
            )
            catchall_violation = (
                target_slot is not None
                and prior_catchall_turns >= 1
                and self._is_catchall_question(llm_resp.assistant_response)
            )
            # User directive (2026-07-25, "슬롯 기반 유도 질문은 협상 불가 핵심
            # 기능"): a non-crisis round-robin turn with a real target slot
            # must always end in a question — a candidate that ships pure
            # empathy with NO question at all is a defect in itself, not a
            # style variance the near-dup/catch-all checks (which all
            # require a "?" to even be evaluated) are equipped to catch.
            # Live repro: session `db6da0e2` turn 4 shipped "잠을 잘 못
            # 주무시고 짜증이 많이 나셨겠어요. 그럴 때는 정말 지치고
            # 힘들죠." — zero "?", no guard fired (not near-dup, not
            # catch-all, not output-isolation) — the model simply omitted
            # the follow-up question the slot-collection flow requires.
            # Deliberately the most conservative possible test (absence of
            # ANY "?", not a topic/keyword heuristic) — per the same
            # directive's false-positive-cost principle, this can only ever
            # under-fire (miss a vague-but-technically-a-question reply),
            # never over-fire and strip a genuine question.
            question_missing = (
                target_slot is not None
                and "?" not in llm_resp.assistant_response
            )
            # CVR-056 finding 3 / REV-022 §4: the SI-screen/risk-targeted
            # turn (either mechanism that can produce it — the forced probe
            # path or the plain round-robin independently landing on
            # `risk_assessment`, both of which set `risk_question_pending`
            # True for THIS render, see `OrchestratorAgent._resolve_
            # dialogue_probe_instruction`) must ask exactly ONE question.
            # Live repro (`logs_run1_natural_requery` t5): a self-harm/SI
            # question and an other-directed-harm question compounded into
            # one turn (`question_mark_count: 2`) — a single denial reply
            # cannot be attributed to either construct with confidence.
            # Crisis-turn-scoped ONLY (never applied to ordinary chit-chat
            # turns, per the user's anti-forcing principle) — general
            # multi-question turns elsewhere are NOT this guard's concern.
            # BUG-083 item 3 closure (2026-07-25, user-reported live P0,
            # session `04cfe927`) / BUG-085-follow-up: this predicate was
            # scoped to `risk_question_pending` ONLY (the mandatory SI
            # screen OUTSIDE probe mode) — BUG-083's own resolution note
            # already flagged this exact gap as open ("risk_question_
            # missing/risk_compound_violation guards remain scoped to
            # risk_question_pending only, probe_active turns still
            # unguarded"). Live confirmation: session `04cfe927` turn 6 —
            # the graduated Safety Probe (`probe_instruction` active,
            # `target_slot` is None so `question_missing`/`catchall_
            # violation` are also inert) shipped a candidate crammed with
            # 5 question marks with NO guard able to even evaluate it,
            # because `risk_compound_violation` alone required
            # `risk_question_pending`, which is a DIFFERENT flag from
            # `probe_instruction`/`probe_active`. Widened to treat any
            # probe-active turn (`session_state["probe_instruction"]`
            # truthy — the SAME signal `_resolve_round_robin_target` reads
            # to null out `target_slot`) as risk-target-scoped too, so the
            # existing `risk_compound_violation`/`risk_question_missing`
            # guards (and their existing exhaustion-path composers) now
            # also cover the 4-stage probe, closing the gap with zero new
            # violation types.
            is_risk_target_turn = bool(
                (inp.session_state or {}).get("risk_question_pending")
                or (inp.session_state or {}).get("probe_instruction")
            )
            risk_compound_violation = (
                is_risk_target_turn
                and llm_resp.assistant_response.count("?") >= 2
            )
            # BUG-082 (2026-07-25, live): `question_missing`'s own
            # precondition (`target_slot is not None`) is structurally
            # False on every probe-mode turn (`_resolve_round_robin_target`
            # returns `None` whenever `probe_instruction`/an active SI
            # screen is set, by design — see that method's docstring), so
            # the ONLY question-presence guard active during an SI screen
            # was `risk_compound_violation`, which only catches `count("?")
            # >= 2` — a `count("?") == 0` candidate on an active SI-screen
            # turn was invisible to BOTH guards simultaneously. Live repro:
            # session `b28a1900...` turn 4, a genuine explicit SI denial
            # got the reply "그런 변화가 있었군요." — zero "?", shipped
            # unmodified, `risk_question_pending` left `True` indefinitely
            # with no re-ask. Independent of `target_slot` by design (fix
            # direction (a), not (b) — threading `target_slot="risk_
            # assessment"` on probe turns risked reintroducing `target_
            # mismatch`/`catchall_violation` false positives on those same
            # turns, since those guards also key off `target_slot`).
            risk_question_missing = (
                is_risk_target_turn
                and "?" not in llm_resp.assistant_response
            )
            # BUG-085-follow-up (session `04cfe927`, turns 7-10): a SEPARATE
            # failure mode from `risk_question_missing`/`risk_compound_
            # violation` above — the candidate contains exactly ONE question
            # mark, so neither of those guards fires, but the question is
            # about the WRONG topic: the model ignored `probe_instruction`'s
            # assigned stage (live repro: stage was "plan" — "혹시 구체적인
            # 계획을 생각해 본 적이 있는지" — but the rendered question asked
            # a chief_complaint-shaped generic reflection, "가장 견디기
            # 힘드신 점이 무엇인지", 4 turns straight). `target_slot`-scoped
            # `catchall_violation`/`target_mismatch` cannot catch this
            # (`target_slot` is None on every probe turn by design).
            # `infer_literal_probe_stage` — the SAME primitive
            # `OrchestratorAgent._advance_safety_probe` already uses to
            # validate a PRIOR turn's rendering before scoring a reply
            # against it — applied to THIS candidate detects when its
            # question cannot be tied to the stage the model was told to
            # ask about.
            probe_topic_mismatch = (
                expected_probe_stage is not None
                and "?" in llm_resp.assistant_response
                and infer_literal_probe_stage(llm_resp.assistant_response)
                != expected_probe_stage
            )

            if internal_leak:
                violation: str | None = "internal_leak"
            elif isolation_reason:
                violation = f"output_isolation_{isolation_reason}"
            elif self_ref_relief_violation:
                # CVR-039 finding 5 / PLAN-2026-W30 cluster B #2: banned
                # counselor self-referential relief content ("다행"-root)
                # must never ship — ranked above `presence_missing` (a
                # candidate carrying this content already has an empathy
                # clause per `_EMPATHY_MARKERS`, so `presence_missing`
                # would not fire on it anyway; explicit ordering documents
                # that this is the intended, higher-severity classification
                # for that candidate) and above the near-dup/repeat checks
                # (banned content is a content-correctness failure, not a
                # variety failure).
                violation = "self_referential_relief"
            elif presence_missing:
                violation = "presence_missing"
            elif risk_compound_violation:
                violation = "risk_compound_question"
            elif risk_question_missing:
                violation = "risk_question_missing"
            elif probe_topic_mismatch:
                violation = "probe_topic_mismatch"
            elif catchall_violation:
                violation = "target_mismatch"
            elif question_missing:
                violation = "question_missing"
            elif is_repeated:
                violation = "exact_repeat"
            elif near_dup_reason:
                violation = f"near_dup_{near_dup_reason}"
            elif leading_prefix_repeat:
                violation = "leading_prefix_repeat"
            elif question_dup_reason:
                # Deliberately NOT prefixed "near_dup" — `_is_empathy_
                # degradable` routes any `near_dup*` violation to the
                # LEADING-empathy-clause text-surgery degrade path on
                # budget exhaustion, which would ship the still-repeated
                # question span byte-identical (its own hard constraint).
                # This violation has no safe degrade; exhaustion falls
                # through to `fall_through=True` (shipped + logged), same
                # as any other non-degradable violation type.
                violation = f"question_repeat_{question_dup_reason}"
            else:
                violation = None

            if violation is None:
                break

            if retry_count >= _MAX_REGENERATION_ATTEMPTS:
                if violation == "target_mismatch":
                    # BUG-077 item (A) safety net (this branch is only
                    # reachable when `prior_catchall_turns >= 1` — see the
                    # `catchall_violation` computation above; the session's
                    # first catch-all never reaches here at all): the retry
                    # regenerations above already gave the model a chance to
                    # self-correct using the visibility hint
                    # (`_build_retry_hint`'s "target_mismatch" branch); once
                    # that budget is exhausted on a REPEAT catch-all, force a
                    # deterministic target-bound question instead of
                    # shipping a third occurrence.
                    degraded_text = DialogueAgent._force_target_question(
                        llm_resp.assistant_response, target_slot,
                    )
                    logger.warning(
                        "DialogueAgent target-binding safety net exhausted "
                        "retry budget (%d) — this catch-all repeats a prior "
                        "one this session — forcing a deterministic "
                        "target-bound question instead of shipping another "
                        "one, unresolved violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    exhaustion_degrade = violation
                    exhaustion_degrade_phrase = target_slot
                    llm_resp = DialogueLLMResponse(
                        assistant_response=degraded_text,
                        reason_summary=(
                            "target-binding safety net exhausted retry "
                            "budget — repeat catch-all question, "
                            "deterministic target-bound question forced"
                        ),
                    )
                    break
                if violation == "risk_question_missing":
                    # BUG-082 exhaustion path: mirrors `question_missing`'s
                    # own forced-question fallback, but `target_slot` is
                    # `None` on every probe-mode turn by design (see the
                    # `risk_question_missing` computation above) — compose
                    # the deterministic SI re-ask directly (`_SLOT_QUESTION_
                    # GUIDE["risk_assessment"]`'s topic, not a raw slot-key
                    # lookup against `None`) rather than passing `target_
                    # slot` through unchanged.
                    degraded_text = DialogueAgent._force_target_question(
                        llm_resp.assistant_response, "risk_assessment",
                    )
                    logger.warning(
                        "DialogueAgent risk-question-presence safety net "
                        "exhausted retry budget (%d) — active SI-screen turn "
                        "shipped zero question marks — forcing a "
                        "deterministic SI re-ask, unresolved violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    exhaustion_degrade = violation
                    exhaustion_degrade_phrase = "risk_assessment"
                    llm_resp = DialogueLLMResponse(
                        assistant_response=degraded_text,
                        reason_summary=(
                            "risk-question-presence guard exhausted retry "
                            "budget — no question in candidate on an active "
                            "SI-screen turn, deterministic SI re-ask forced"
                        ),
                    )
                    break
                if violation == "probe_topic_mismatch":
                    # BUG-085-follow-up (session `04cfe927`): the retries
                    # above already gave the model 2 chances to self-correct
                    # onto `expected_probe_stage`'s topic via the hint below
                    # — on exhaustion, compose the stage-bound question
                    # deterministically instead of shipping another
                    # off-topic rendering (same "never lose the mandated
                    # topic" discipline `_force_target_question` applies to
                    # round-robin turns, here applied to the probe's own
                    # stage topic via `_force_probe_question`).
                    degraded_text = DialogueAgent._force_probe_question(
                        llm_resp.assistant_response, expected_probe_stage,
                    )
                    logger.warning(
                        "DialogueAgent probe-topic safety net exhausted "
                        "retry budget (%d) — candidate's question could not "
                        "be tied to the assigned probe stage ('%s') — "
                        "forcing a deterministic stage-bound question, "
                        "unresolved violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS, expected_probe_stage,
                        retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    exhaustion_degrade = violation
                    exhaustion_degrade_phrase = expected_probe_stage
                    llm_resp = DialogueLLMResponse(
                        assistant_response=degraded_text,
                        reason_summary=(
                            "probe-topic guard exhausted retry budget — "
                            "deterministic stage-bound question forced"
                        ),
                    )
                    break
                if violation == "question_missing":
                    # User directive (2026-07-25): a collection turn's
                    # fallback must NEVER drop the question — append a
                    # deterministic target-bound question (same composer as
                    # `target_mismatch`'s own forced path) rather than
                    # shipping the empathy-only candidate as-is
                    # (`fall_through` would otherwise ship exactly the
                    # question-less text this guard exists to prevent).
                    degraded_text = DialogueAgent._force_target_question(
                        llm_resp.assistant_response, target_slot,
                    )
                    logger.warning(
                        "DialogueAgent question-presence safety net exhausted "
                        "retry budget (%d) — candidate had no question mark at "
                        "all — forcing a deterministic target-bound question, "
                        "unresolved violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    exhaustion_degrade = violation
                    exhaustion_degrade_phrase = target_slot
                    llm_resp = DialogueLLMResponse(
                        assistant_response=degraded_text,
                        reason_summary=(
                            "question-presence guard exhausted retry budget — "
                            "no question in candidate, deterministic "
                            "target-bound question forced"
                        ),
                    )
                    break
                if violation == "risk_compound_question":
                    # CVR-056 finding 3 / REV-022 §4: crisis-turn-scoped
                    # question-count safety net — truncate to the FIRST
                    # question span only (deterministic text surgery, no new
                    # LLM call), same "never lose the question, never keep
                    # more than the crisis-turn allows" discipline as the
                    # other forced paths above.
                    degraded_text = DialogueAgent._truncate_to_first_question(
                        llm_resp.assistant_response,
                    )
                    logger.warning(
                        "DialogueAgent risk-turn compound-question safety net "
                        "exhausted retry budget (%d) — SI-screen turn asked "
                        "%d questions — truncating to the first question only, "
                        "unresolved violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS,
                        llm_resp.assistant_response.count("?"),
                        retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    exhaustion_degrade = violation
                    exhaustion_degrade_phrase = None
                    llm_resp = DialogueLLMResponse(
                        assistant_response=degraded_text,
                        reason_summary=(
                            "risk-turn compound-question guard exhausted retry "
                            "budget — truncated to the first question only"
                        ),
                    )
                    break
                if violation.startswith("output_isolation") or violation == "internal_leak":
                    # BUG-037 exhaustion path (extended for `internal_leak`,
                    # coordinator directive 2026-07-25): the violating text
                    # is NOT a valid patient-facing message (internal
                    # clinical-note register, a mechanical echo, or a raw
                    # slot-key/internal-term leak) — unlike the other three
                    # checks, falling through and shipping it verbatim is
                    # not an acceptable degrade. Ship a minimal neutral
                    # continuation instead and flag it distinctly from
                    # `fall_through` (whose field contract specifically
                    # means "the violating text was shipped anyway" — that
                    # is precisely what must NOT happen here).
                    logger.warning(
                        "DialogueAgent output-isolation/internal-leak guard "
                        "exhausted retry budget (%d) — shipping neutral "
                        "fallback instead of violating text, unresolved "
                        "violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    output_isolation_fallback = True
                    llm_resp = DialogueLLMResponse(
                        assistant_response=_OUTPUT_ISOLATION_FALLBACK_RESPONSE,
                        reason_summary=(
                            "output-isolation/internal-leak guard exhausted "
                            "retry budget — neutral fallback shipped instead "
                            "of clinical-note/echo/internal-identifier text"
                        ),
                    )
                    break
                if target_slot is not None and (
                    violation.startswith("question_repeat") or question_dup_reason
                ):
                    # BUG-084a (2026-07-25, user-reported live P0, session
                    # `94f75e81`): the repeated CONTENT here is the
                    # QUESTION, not the empathy lead-in — `_degrade_empathy_
                    # clause` only ever splices the leading-clause span
                    # BYTE-IDENTICAL from the terminal punctuation onward
                    # (its own hard constraint), so routing a question-
                    # content repeat through it ships the same
                    # already-answered/already-grounded question verbatim
                    # with only the empathy phrase swapped — exactly the
                    # live symptom ("...substance_use_history grounded as a
                    # bare denial... no re-ask needed" immediately followed
                    # by the SAME substance-use question shipped again).
                    # This fires whenever the CURRENT candidate's question
                    # span repeats (either the `question_repeat_*` violation
                    # itself, which `_is_empathy_degradable` never matches
                    # and would otherwise fall through unresolved — see
                    # that violation's own `elif` comment above — OR a
                    # `near_dup_*` empathy-clause violation whose trailing
                    # question ALSO independently repeats this same
                    # iteration, `question_dup_reason`, which previously lost
                    # to `_degrade_empathy_clause`'s empathy-only splice).
                    # `target_slot` (this turn's own already-resolved
                    # round-robin target — by construction NOT an
                    # already-grounded/already-filled slot, see
                    # `_resolve_round_robin_target`/`compute_target_slot`)
                    # is used to force a fresh, on-topic, deterministic
                    # question via the SAME composer `target_mismatch`'s own
                    # exhaustion path uses — a genuine topic-switch away
                    # from whatever slot the model kept repeating, never a
                    # cosmetic empathy-only substitution.
                    degraded_text = DialogueAgent._force_target_question(
                        llm_resp.assistant_response, target_slot,
                    )
                    logger.warning(
                        "DialogueAgent question-repeat safety net exhausted "
                        "retry budget (%d) — repeated question content "
                        "targeting an already-answered/already-grounded "
                        "topic — forcing a deterministic different-topic "
                        "question instead of an empathy-only degrade, "
                        "unresolved violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    exhaustion_degrade = violation
                    exhaustion_degrade_phrase = target_slot
                    llm_resp = DialogueLLMResponse(
                        assistant_response=degraded_text,
                        reason_summary=(
                            "question-repeat guard exhausted retry budget — "
                            "deterministic target-bound question forced "
                            "instead of an empathy-only degrade"
                        ),
                    )
                    break
                if DialogueAgent._is_empathy_degradable(violation):
                    # Fix 2 — Option C (`docs/ai/fix_design_exhaustion_
                    # bug037.md` §3, ADR-030 Decisions 1/2): safe degrade
                    # of the leading empathy clause ONLY, instead of
                    # shipping the detected-violating text as-is
                    # (`fall_through`). Covers every currently-enumerated
                    # violation type other than `output_isolation_*`
                    # (handled above) — the generic `fall_through` branch
                    # below is therefore unreachable under today's
                    # violation set; kept as a defensive catch-all for any
                    # future violation type this branch is not updated to
                    # degrade. Zero extra LLM calls — pure text surgery on
                    # the already-generated last candidate.
                    degraded_text, substituted_phrase = (
                        DialogueAgent._degrade_empathy_clause(
                            llm_resp.assistant_response, violation,
                            inp.conversation_history,
                        )
                    )
                    logger.warning(
                        "DialogueAgent guard exhausted retry budget (%d) — "
                        "degrading empathy clause instead of shipping "
                        "violating text, unresolved violation(s) %s",
                        _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
                    )
                    retry_reasons.append(violation)
                    exhaustion_degrade = violation
                    exhaustion_degrade_phrase = substituted_phrase
                    llm_resp = DialogueLLMResponse(
                        assistant_response=degraded_text,
                        reason_summary=(
                            "empathy-degrade guard exhausted retry budget — "
                            "leading empathy clause substituted with a pool "
                            "phrase"
                        ),
                    )
                    break
                fall_through = True
                logger.warning(
                    "DialogueAgent guard exhausted retry budget (%d) — shipping "
                    "with unresolved violation(s) %s",
                    _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
                )
                retry_reasons.append(violation)
                break

            retry_count += 1
            retry_reasons.append(violation)
            logger.warning(
                "DialogueAgent guard violation (%s) — retry %d/%d",
                violation, retry_count, _MAX_REGENERATION_ATTEMPTS,
            )
            hint = self._build_retry_hint(violation, inp, candidate_clause, target_slot)
            messages[-1] = ChatMessage(role="user", content=inp.user_message + hint)
            retry_started = time.perf_counter()
            try:
                resp = await adapter.chat_timed(
                    messages, model=selection.model_id,
                    temperature=0.7, max_tokens=512,
                    response_format=response_format,
                )
                llm_resp = self._parse_response(resp.content)
            except Exception as exc:
                # Same "except: pass"-then-ship semantics the pre-iter-2 code
                # already had for its single retry (design §3) — ship the
                # last successfully-parsed candidate. `fall_through` is
                # deliberately NOT set here: its field contract (§6) and
                # REV-032 criterion D's telemetry invariant
                # (`fall_through ⟹ retry_count == _MAX_REGENERATION_ATTEMPTS`)
                # both scope it to budget exhaustion specifically — an
                # exception can occur on retry 1, which would violate that
                # invariant if flagged here. Logged (never silent) instead.
                logger.warning(
                    "DialogueAgent guard retry LLM call failed: %s — "
                    "shipping last successfully-parsed response", exc,
                )
                break
            finally:
                retry_latency_ms += (time.perf_counter() - retry_started) * 1000

        latency_ms = (time.perf_counter() - started) * 1000

        # CVR-057 qa recommendation #3 (2026-07-25, session `04cfe927`):
        # log which of the 6 discriminant-table utterance types THIS
        # turn's patient message was classified as, and whether the
        # shipped response opened with an empathy clause — telemetry
        # only, does not gate/alter the response, and is deliberately
        # NOT added to `DialogueOutput`'s wire schema (no downstream
        # contract change, ai-server-internal audit trail only per this
        # mission's scope). Enables the future live-data audit CVR-057
        # asks for ("판별표 준수 여부를 라이브 데이터로 자동 감사").
        shipped_empathy = DialogueAgent._is_empathy_clause(
            DialogueAgent._extract_leading_clause(llm_resp.assistant_response)
        )
        logger.info(
            "DialogueAgent utterance_type_classified=%s empathy_shipped=%s "
            "(CVR-057 telemetry, non-blocking)",
            DialogueAgent._classify_utterance_type(inp.user_message, crisis_adjacent),
            shipped_empathy,
        )

        # Dialogue는 응답만 반환 — slot 추출/coverage/risk 판단은 하지 않음
        return DialogueOutput(
            model_used=resp.model,
            prompt_version=PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary=llm_resp.reason_summary,
            assistant_response=llm_resp.assistant_response,
            slot_updates={},          # Slot 추출은 ClinicalSlotAgent의 역할
            risk_level=RiskLevel.none, # 위험도 판단은 SafetyAgent의 역할
            requires_human_review=False,
            all_slots=dict(inp.filled_slots),
            handoff_ready=False,      # Coverage 판단은 f1.py orchestrator의 역할
            prompts_degraded=prompts_degraded,
            retry_count=retry_count,
            retry_reasons=retry_reasons,
            fall_through=fall_through,
            retry_latency_ms=retry_latency_ms,
            crisis_adjacent=crisis_adjacent,
            output_isolation_fallback=output_isolation_fallback,
            near_dup_detail=near_dup_detail,
            exhaustion_degrade=exhaustion_degrade,
            exhaustion_degrade_phrase=exhaustion_degrade_phrase,
        )

    @classmethod
    def missing_questionable_slots(
        cls,
        filled_slots: dict[str, str],
        deferred_slots: set[str] | frozenset[str] | None = None,
    ) -> list[str]:
        """Return question-able slots not yet filled, essential slots first.

        `deferred_slots` (Cluster A, asked-slot generalized fix, additive):
        slots the orchestrator has given up re-asking after
        `_ASK_DEFER_THRESHOLD` unanswered attempts — excluded from the
        round-robin the same way an already-filled slot is, so dialogue
        steering stops re-selecting them for the rest of the session.
        `risk_assessment` is never expected in this set (governed by the
        Cluster C probe/termination gate instead), but no special-casing
        is needed here — a caller simply never puts it in the set.
        """
        deferred = deferred_slots or frozenset()
        filled_keys = {k for k, v in filled_slots.items() if v and k in _ALL_SLOTS}
        questionable_essential = [s for s in _ESSENTIAL_SLOTS if s not in _NO_QUESTION_SLOTS]
        missing_essential = [
            s for s in questionable_essential if s not in filled_keys and s not in deferred
        ]
        missing_other = [
            s for s in _ALL_SLOTS
            if s not in _ESSENTIAL_SLOTS and s not in filled_keys
            and s not in _NO_QUESTION_SLOTS and s not in deferred
        ]
        return missing_essential + missing_other

    @classmethod
    def compute_target_slot(
        cls,
        filled_slots: dict[str, str],
        conversation_history: list[dict[str, str]] | None,
        deferred_slots: set[str] | frozenset[str] | None = None,
    ) -> str | None:
        """Deterministic round-robin target slot for this turn (None = all filled).

        Exposed so the F1 pipeline (and now `OrchestratorAgent`, Cluster A)
        can record which slot the dialogue targeted each turn (needed by
        the grounding filter's ask-evidence rule / the asked-slot
        deferral counter). The result matches _build_slot_context exactly
        for the same inputs. See `missing_questionable_slots` for
        `deferred_slots` semantics.
        """
        all_missing = cls.missing_questionable_slots(filled_slots, deferred_slots=deferred_slots)
        if not all_missing:
            return None

        n_agent_turns = 0
        if conversation_history:
            n_agent_turns = sum(
                1 for m in conversation_history if m.get("role") == "assistant"
            )

        idx = n_agent_turns % len(all_missing)
        target = all_missing[idx]

        # 직전 타겟 재타겟 방지
        if len(all_missing) > 1:
            last_ai = ""
            if conversation_history:
                ai_msgs = [m for m in conversation_history if m.get("role") == "assistant"]
                if ai_msgs:
                    last_ai = ai_msgs[-1]["content"].lower()
            guide_text = _SLOT_QUESTION_GUIDE.get(target, "").lower()
            if guide_text and any(kw in last_ai for kw in guide_text.split()[:3]):
                idx = (idx + 1) % len(all_missing)
                target = all_missing[idx]

        return target

    # ── BUG-077 item (A): target-binding guard primitives ───────────────

    @classmethod
    def _resolve_round_robin_target(cls, inp: DialogueInput) -> str | None:
        """The round-robin target THIS turn's rendered question is
        expected to reflect — same BUG-056 union (`session_state["slot_
        data"]` ∪ caller `filled_slots`) and `compute_target_slot` call
        `_build_slot_context` uses to build its own "이번 턴: {target}에
        대해 질문하세요" instruction, so the guard below validates the
        model's OUTPUT against the exact target the prompt was told to
        steer toward. Returns None on opening/probe-mode turns (no
        round-robin target applies there — the guard is inert)."""
        session_state = inp.session_state or {}
        if session_state.get("opening_turn") or session_state.get("probe_instruction"):
            return None
        deferred_slots = set(session_state.get("deferred_slots") or [])
        orchestrator_slot_data = session_state.get("slot_data") or {}
        unioned_filled = {**orchestrator_slot_data, **inp.filled_slots}
        return cls.compute_target_slot(
            unioned_filled, inp.conversation_history, deferred_slots=deferred_slots,
        )

    @staticmethod
    def _build_asked_topic_history(
        conversation_history: list[dict[str, str]] | None,
    ) -> list[str]:
        """BUG-077 item (A), state-visibility primary mechanism (user
        directive 2026-07-25): pair each prior assistant turn with the
        patient's following reply and infer WHICH slot topic the assistant
        turn literally asked about (`infer_literal_target_slot` — the same
        primitive `OrchestratorAgent`'s BUG-077 attribution fix uses, so
        this ledger cannot disagree with the code's own denial-attribution
        logic). A turn whose literal text resolves to no specific slot is
        shown as "(특정 주제 없는 범용 질문)" rather than silently omitted —
        the model needs to SEE that it already used a generic question once
        in order to reason its own way out of repeating it, rather than a
        rule enforcing that from outside. Capped to the last 6 pairs (avoid
        unbounded prompt growth on long sessions)."""
        if not conversation_history:
            return []
        pairs: list[str] = []
        pending_question: str | None = None
        for m in conversation_history:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                pending_question = content
            elif role == "user" and pending_question is not None:
                slot = infer_literal_target_slot(pending_question)
                label = (
                    _SLOT_QUESTION_GUIDE.get(slot, slot)
                    if slot else "(특정 주제 없는 범용 질문)"
                )
                reply_gist = content if len(content) <= 40 else content[:40] + "..."
                pairs.append(f'  - {label} → 환자 응답: "{reply_gist}"')
                pending_question = None
        return pairs[-6:]

    @staticmethod
    def _is_catchall_question(text: str) -> bool:
        """BUG-077: True when `text`'s substantive/question span cannot be
        tied (via `infer_literal_target_slot`) to any specific
        question-able slot topic — the shape symptomatic of the BUG-077
        repro's repeated "혹시 다른 증상이나 걱정되는 부분은 없으신가요?"
        catch-all. Only meaningful on a round-robin turn (a specific target
        was assigned) — callers gate this on `target_slot is not None`."""
        if not text or "?" not in text:
            return False
        span = DialogueAgent._extract_trailing_clause(text) or text
        return infer_literal_target_slot(span) is None

    @staticmethod
    def _count_prior_catchall_turns(
        conversation_history: list[dict[str, str]] | None,
    ) -> int:
        """BUG-077 session-level cap: count of PRIOR assistant turns this
        session whose rendered text was itself a generic catch-all
        question (per `_is_catchall_question`) — used to allow exactly one
        per session before the exhaustion path force-degrades any further
        occurrence."""
        if not conversation_history:
            return 0
        return sum(
            1
            for m in conversation_history
            if m.get("role") == "assistant"
            and DialogueAgent._is_catchall_question(m.get("content", ""))
        )

    @staticmethod
    def _force_target_question(assistant_response: str, target_slot: str | None) -> str:
        """BUG-077 item (A) exhaustion path (session-level catch-all cap):
        deterministically composes a question that literally names
        `target_slot`'s own guide topic, preserving the candidate's
        leading clause (empathy lead-in, if any — same splice mechanism
        `_degrade_empathy_clause` uses via `_splice_point`) so only the
        QUESTION span is replaced. Zero new LLM call. Used only once the
        retry budget is exhausted AND a generic catch-all question has
        already shipped once this session (the session-level cap) — the
        session's first catch-all is instead tolerated via fall-through.

        BUG-079 (user directive 2026-07-25): composed as a literal "?"
        question ("...대해 여쭤봐도 될까요?"), not a declarative "I'd like
        to ask about..." statement — this is now also the shared exhaustion
        fallback for `question_missing`, whose whole contract is "the
        shipped text must contain a question"; a declarative composition
        would defeat its own guard.

        BUG-082 note: `_SLOT_QUESTION_GUIDE["risk_assessment"]` carries a
        trailing parenthetical that is an internal composer instruction
        ("(반드시 한 가지만 물어야 함)"), not patient-facing content — strip
        any trailing " (...)" annotation before composing so it never leaks
        into the deterministic question text shipped to the patient."""
        guide = _SLOT_QUESTION_GUIDE.get(target_slot or "", target_slot or "")
        guide = re.sub(r"\s*\([^()]*\)\s*$", "", guide).strip()
        question = f"{guide}에 대해 여쭤봐도 될까요?"
        end = DialogueAgent._splice_point(assistant_response)
        if end is not None:
            leading = assistant_response[: end + 1].strip()
            if leading:
                return f"{leading} {question}"
        return question

    @staticmethod
    def _force_probe_question(
        assistant_response: str, expected_probe_stage: str | None,
    ) -> str:
        """BUG-085-follow-up (session `04cfe927`) exhaustion path for
        `probe_topic_mismatch`: deterministically composes a question
        naming `expected_probe_stage`'s own `PROBE_STAGES` hint (the SAME
        text `safety_probe.build_probe_instruction` embeds into the
        prompt directive), preserving the candidate's leading clause via
        the same splice mechanism `_force_target_question` uses. Zero new
        LLM call. Falls back to a generic (but still on-topic-neutral,
        never a chief_complaint-style substitute) safety-check phrasing
        if `expected_probe_stage` is somehow unrecognized (defensive —
        should not happen, this is only ever called when the caller's own
        `probe_topic_mismatch` computation found a non-None expected
        stage)."""
        hint = _PROBE_STAGE_HINTS.get(expected_probe_stage or "", "")
        question = f"{hint} 여쭤봐도 될까요?" if hint else "조금 더 자세히 말씀해 주시겠어요?"
        end = DialogueAgent._splice_point(assistant_response)
        if end is not None:
            leading = assistant_response[: end + 1].strip()
            if leading:
                return f"{leading} {question}"
        return question

    @staticmethod
    def _truncate_to_first_question(assistant_response: str) -> str:
        """CVR-056 finding 3 exhaustion path: keep everything up to and
        including the FIRST "?" only, dropping any second (or further)
        question span — deterministic text surgery, zero new LLM call.
        Used only on the crisis/SI-screen turn (`risk_compound_question`),
        never on an ordinary collection turn. Falls back to returning the
        text unchanged if it somehow contains no "?" at all (defensive —
        this violation type is only ever computed on text with
        `count("?") >= 2`, so this branch should be unreachable in
        practice)."""
        idx = assistant_response.find("?")
        if idx == -1:
            return assistant_response
        return assistant_response[: idx + 1].strip()

    # ── BUG-030 iter-2 / BUG-035 guard primitives ──────────────────────
    # (`_archive/plans/fix_design_bug030_iter2.md` §1/§4/§5, ADR-029)

    @staticmethod
    def _extract_leading_clause(text: str) -> str:
        """Leading clause up to (not including) the first '.', '!', or '?' —
        no length cap. Replaces the old `[:30]`-capped, `.`/`?`-only split
        (fix_proposal_bug030.md finding c-v: a cap silently under-matches
        any clause >30 chars). If the earliest terminal punctuation found is
        '?', the response opens directly with a question — no leading
        clause exists (return ""). If no terminal punctuation exists at
        all, conservatively return "" rather than guess a boundary.
        Delegates the boundary rule to the module-level
        `_leading_clause_boundary` (shared with `_splice_point` below)."""
        stripped = text.strip()
        if not stripped:
            return ""
        end = _leading_clause_boundary(stripped)
        if end is None:
            return ""
        return stripped[:end].strip()

    @staticmethod
    def _splice_point(text: str) -> int | None:
        """Fix 2 (`_archive/plans/fix_design_exhaustion_bug037.md` §3): the same
        clause boundary `_extract_leading_clause` locates, but returned as
        a raw index into the ORIGINAL (unstripped) `text` — so a caller can
        slice `text[end:]` and get a remainder that is byte-identical to
        what the model generated. That is the hard constraint the degrade
        mechanism must satisfy: only the span BEFORE this index may ever
        be replaced. None means there is no boundary to splice at (mirrors
        `_extract_leading_clause`'s "" case) — callers must fail safe
        (prepend, never guess a boundary) when this is None."""
        return _leading_clause_boundary(text)

    @staticmethod
    def _is_empathy_clause(clause: str) -> bool:
        """Deterministic, string-level, Korean-marker-based check: does
        `clause` read as an affective acknowledgment? Marker set per
        ADR-029 Decision 2 (REV-032 Issue 1 ∩ CVR-011 Finding 5) — bare
        "겠" removed (false-positive risk on procedural Korean like
        "여쭤보겠습니다"); "-군요" family added (reflective-acknowledgment
        coverage). Governs retry-triggering only — rubric §10.1's own
        semantic test, not this marker list, governs the EXP-018
        acceptance verdict (CVR-011 Finding 5)."""
        return bool(clause) and any(m in clause for m in _EMPATHY_MARKERS)

    @staticmethod
    def _banned_self_referential_relief_violation(text: str) -> bool:
        """CVR-039 finding 5 / PLAN-2026-W30 cluster B #2
        (`experiments/EXP-030/plan.md` §3): does `text` carry counselor
        self-referential relief content ("다행"-root — e.g.
        "다행이에요"/"다행입니다"/"다행이네요")? This is the content-level
        ban CVR-038 finding 1 already stated at the prompt layer (v5's
        공감 캘리브레이션 section) but which CVR-039's real transcripts
        show the model does not reliably follow (B1/B2/B3 recurrence) —
        `_EMPATHY_MARKERS` only detects empathy-clause PRESENCE, never
        banned CONTENT (plan.md §3 cluster B row, CONFIRMED gap); this
        closes that gap deterministically.

        Deliberately root-only (`_BANNED_SELF_REFERENTIAL_RELIEF_MARKERS`
        = `("다행",)`), not a "다행 root + separately-detected positive
        frame" compound check: "다행" itself always denotes the
        speaker's own relief/fortunate framing in Korean, so no extra
        polarity signal is needed to disambiguate it, and it never
        overlaps the allowed "감사"-root patient-directed gratitude
        family (CVR-038's own distinguishing example swap) — a
        legitimate "감사해요"/"그런 변화가 있었군요" clause cannot match.

        CVR-041 pin (widened scope, EXP-030 pin-fix wave): scans the
        caller-supplied `text` verbatim — the caller now passes the FULL
        `assistant_response`, not just the leading clause, closing
        CVR-041 finding 1 (a same-turn SECOND clause carrying "다행" went
        completely undetected under the old leading-clause-only scope).
        CVR-041 confirmed this widening carries low false-positive risk
        (the "다행" root never overlaps the allowed "감사"/"~군요"
        families). The retry-EXHAUSTION degrade path
        (`_degrade_empathy_clause`) still only splices the leading-clause
        span — see the call site's own comment for that residual, honestly
        disclosed scope boundary."""
        return bool(text) and any(
            m in text for m in _BANNED_SELF_REFERENTIAL_RELIEF_MARKERS
        )

    @staticmethod
    def _extract_used_empathy_clauses(
        conversation_history: list[dict[str, str]] | None,
    ) -> list[str]:
        """Full-session (unwindowed), no-cap extraction of every prior
        assistant turn's leading clause — ONE entry per turn, in
        chronological order, INCLUDING exact repeats. Shared by
        `_build_slot_context`'s X-list (which locally dedupes this list
        for the SHOWN prompt hint — see that call site) and the retry
        guard below (which needs the raw, undeduped, FULL session list to
        enforce rubric §2's session-wide <=2-uses / zero-back-to-back
        bar).

        BUG-036 fix (2026-07-12, `_archive/plans/fix_design_exhaustion_bug037.md`
        §2, PLAN-2026-W28-U): the prior version deduped by exact string
        (`if clause not in used: used.append(clause)`), which silently
        dropped every exact-repeat occurrence. That broke two things once
        an intervening distinct clause (the A-B-A shape) had registered:
        (a) the back-to-back check's `session_clauses[-1]` pointer
        permanently desynced from the true immediately-preceding turn
        (it kept pointing at the last NEWLY-INTRODUCED distinct clause,
        not the last USED clause); (b) the session-cap's
        `prior_family_count` undercounted true per-family usage, since an
        exact-repeat family could never contribute more than 1 list
        entry — making the >=2-prior-uses cap structurally unreachable
        via exact repeats, the dominant real-world repetition shape.
        Returning every occurrence (no dedup) fixes both: adjacency and
        counts are now computed over the true per-turn sequence."""
        used: list[str] = []
        if not conversation_history:
            return used
        for m in conversation_history:
            if m.get("role") == "assistant":
                clause = DialogueAgent._extract_leading_clause(m["content"])
                if clause:
                    used.append(clause)
        return used

    @staticmethod
    def _extract_trailing_clause(text: str) -> str:
        """BUG-048 Finding (b): the substantive span AFTER any leading
        clause — the SAME boundary `_extract_leading_clause` locates
        (`_leading_clause_boundary`), sliced from the other side. When
        there is no leading-clause boundary (the response opens directly
        with '?', or has no terminal punctuation at all — `_extract_
        leading_clause`'s own "" case), the trailing clause IS the whole
        response: there is no prefix to strip."""
        stripped = text.strip()
        if not stripped:
            return ""
        end = _leading_clause_boundary(stripped)
        if end is None:
            return stripped
        return stripped[end + 1 :].strip()

    @staticmethod
    def _extract_used_trailing_clauses(
        conversation_history: list[dict[str, str]] | None,
    ) -> list[str]:
        """BUG-048 Finding (b): mirrors `_extract_used_empathy_clauses`
        exactly (full-session, unwindowed, no dedup — every prior
        assistant turn's trailing/substantive clause, in chronological
        order, including exact repeats) but for the post-empathy span, so
        the session-cap/back-to-back check below can catch a repeated
        follow-up QUESTION even while the empathy lead-in legitimately
        varies turn to turn."""
        used: list[str] = []
        if not conversation_history:
            return used
        for m in conversation_history:
            if m.get("role") == "assistant":
                clause = DialogueAgent._extract_trailing_clause(m["content"])
                if clause:
                    used.append(clause)
        return used

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Pure-stdlib edit distance (Wagner-Fischer DP,
        O(len(a)*len(b))). Empathy clauses are short; no external
        dependency needed or added."""
        m, n = len(a), len(b)
        if m == 0:
            return n
        if n == 0:
            return m
        prev = list(range(n + 1))
        for i in range(1, m + 1):
            curr = [i] + [0] * n
            for j in range(1, n + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            prev = curr
        return prev[n]

    @staticmethod
    def _same_phrase_family(a: str, b: str) -> bool:
        """rubric_bug030_acceptance.md §1's near-duplicate rule: same
        family if token Jaccard >= 0.5 OR normalized edit distance <= 0.3.
        Normalization: strip surrounding whitespace only (punctuation
        kept — REV-032 criterion A.1 pins this convention as
        punctuation-INCLUSIVE, matching the production code; see the
        design note §2 "as-implemented amendments" for the corrected
        citation); tokenize on whitespace (어절 units), no stemming."""
        a_n, b_n = a.strip(), b.strip()
        if not a_n or not b_n:
            return False
        tokens_a, tokens_b = set(a_n.split()), set(b_n.split())
        union = tokens_a | tokens_b
        if union and len(tokens_a & tokens_b) / len(union) >= _NEAR_DUP_JACCARD_THRESHOLD:
            return True
        ned = DialogueAgent._levenshtein(a_n, b_n) / max(len(a_n), len(b_n))
        return ned <= _NEAR_DUP_NED_THRESHOLD

    @staticmethod
    def _empathy_repetition_violation(
        candidate_clause: str, session_clauses: list[str],
    ) -> str | None:
        """Operationalizes rubric §2 exactly: zero back-to-back (checked
        first, zero-tolerance even on a single prior use) + session cap of
        2 uses per phrase family (checked second — a 3rd same-family use
        violates). Returns a reason string or None. `session_clauses` must
        be the FULL, unwindowed session list."""
        if not candidate_clause or not session_clauses:
            return None
        if DialogueAgent._same_phrase_family(candidate_clause, session_clauses[-1]):
            return "back_to_back"
        prior_family_count = sum(
            1 for c in session_clauses
            if DialogueAgent._same_phrase_family(candidate_clause, c)
        )
        if prior_family_count >= 2:
            return "session_cap"
        return None

    @staticmethod
    def _leading_prefix_repeat_violation(
        candidate_clause: str, session_clauses: list[str],
    ) -> bool:
        """Last-resort safety net (2026-07-25, live re-verification):
        `_empathy_repetition_violation` above only ever runs when
        `_is_empathy_clause(candidate_clause)` is True — a phrase whose
        leading clause functions as an empathy lead-in but does not
        literally contain one of `_EMPATHY_MARKERS`' fixed substrings
        (live repro: "잠 못 드는 상황이 계속되면 마음이 지칠 수 있어요" —
        "지칠" does not match the marker list's "지치셨"/"지치시") is
        invisible to that guard entirely, and to `exact_repeat` too (the
        FULL response differs — only the leading clause repeats). Shipped
        byte-identically 4 turns in a row live, despite the prompt-level
        state-visibility X-list (`_build_slot_context`'s "이미 사용했으므로
        절대 다시 사용하지 마세요") already showing it every turn.

        Per the user's stated priority (state-visibility first, hard guard
        only as a last resort): fires ONLY once the CURRENT candidate would
        be the 3rd byte-identical occurrence IN A ROW (not `_empathy_
        repetition_violation`'s single-prior-use `back_to_back`, and
        independent of `_is_empathy_clause`) — deliberately the narrowest
        possible trigger, so it can only ever catch a genuine, already-
        repeated-twice verbatim prefix, never a stylistic near-miss."""
        if not candidate_clause or len(session_clauses) < 2:
            return False
        clause = candidate_clause.strip()
        return (
            session_clauses[-1].strip() == clause
            and session_clauses[-2].strip() == clause
        )

    @staticmethod
    def _family_count(candidate_clause: str, session_clauses: list[str]) -> int:
        """BUG-036 telemetry helper (`docs/ai/fix_design_exhaustion_
        bug037.md` §2): count of PRIOR occurrences in `session_clauses`
        sharing `candidate_clause`'s phrase family (per
        `_same_phrase_family`). Mirrors the counting
        `_empathy_repetition_violation` does internally for its
        session-cap branch, exposed separately so telemetry can record
        "family, count" (BUG-036 resolution-recommendation) without
        changing that function's tested `str | None` return contract."""
        if not candidate_clause:
            return 0
        return sum(
            1 for c in session_clauses
            if DialogueAgent._same_phrase_family(candidate_clause, c)
        )

    # ── Fix 2 — retry-budget-exhaustion safe degrade primitives ────────
    # (`_archive/plans/fix_design_exhaustion_bug037.md` §3, ADR-030 Decisions 1/2)

    @staticmethod
    def _exclude_degrade_marker_clauses(clauses: list[str]) -> list[str]:
        """ADR-030 Decision 1 / REV-034 live finding: drop any clause the
        SYSTEM itself inserted via a safe-degrade/fallback mechanism (see
        `_DEGRADE_MARKER_CLAUSES`) from the production near-dup guard's
        population — guard-drift prevention. Applied ONLY to `run()`'s own
        `session_clauses` (the back-to-back/session-cap check); NOT
        applied to `_build_slot_context`'s X-list (`used_empathy`), where
        surfacing a previously-shipped degrade phrase to the model as
        "don't reuse this" is harmless (arguably desirable) and out of
        REV-034's stated scope (production guard drift, not the prompt
        hint)."""
        return [c for c in clauses if c not in _DEGRADE_MARKER_CLAUSES]

    @staticmethod
    def _select_degrade_phrase(
        conversation_history: list[dict[str, str]] | None,
    ) -> str:
        """Requirement 1(c) — deterministic, session-scoped rotation: no
        randomness, reproducible. Picks the first `_EMPATHY_DEGRADE_POOL`
        entry NOT already shipped as a degrade clause earlier in THIS
        session, so consecutive degrade events within one session don't
        ship the identical substitute. Looks at the RAW per-turn
        extraction (every assistant turn's leading clause, unfiltered) —
        not the guard-facing `session_clauses`, which has degrade clauses
        excluded from it by design (`_exclude_degrade_marker_clauses`) —
        so a prior degrade IS visible here even though it is invisible to
        the near-dup guard. Wraps around to the first pool entry once
        every entry has been used this session (a repeated pool phrase 5+
        degrades into one session is an accepted residual of a small
        last-resort pool — not the normal generation path, per the design
        note's own disclosed trade-off)."""
        used = {
            DialogueAgent._extract_leading_clause(m["content"])
            for m in (conversation_history or [])
            if m.get("role") == "assistant"
        }
        for phrase in _EMPATHY_DEGRADE_POOL:
            if phrase not in used:
                return phrase
        return _EMPATHY_DEGRADE_POOL[0]

    @staticmethod
    def _is_empathy_degradable(violation: str) -> bool:
        """Fix 2 scope (ADR-030 Decision 2, CVR-013 F1 required follow-
        up): every exhaustion path the safe-degrade mechanism covers —
        `near_dup_*`, `presence_missing`, `exact_repeat`.
        `output_isolation_*` is handled by its own, higher-priority Fix-3
        exhaustion branch and never reaches this check (see `run()`'s
        exhaustion dispatch, which tests `output_isolation` first).
        `self_referential_relief` added (CVR-039 finding 5 / PLAN-2026-W30
        cluster B #2): the banned "다행"-root clause is itself an empathy
        clause per `_EMPATHY_MARKERS` (added for exactly this purpose), so
        `_degrade_empathy_clause` REPLACES it with a pool phrase rather
        than merely prepending one — the banned text must not ship at
        all, not just be preceded by something else. `leading_prefix_
        repeat` added (2026-07-25, live): the guard's whole definition IS
        "this leading clause is the 3rd byte-identical occurrence in a
        row" — always safe to REPLACE (see `_degrade_empathy_clause`'s
        own override for this violation type, which skips the `_is_
        empathy_clause` gate other REPLACE cases require)."""
        return (
            violation == "presence_missing"
            or violation == "exact_repeat"
            or violation == "self_referential_relief"
            or violation == "leading_prefix_repeat"
            or violation.startswith("near_dup")
        )

    @staticmethod
    def _degrade_empathy_clause(
        assistant_response: str,
        violation: str,
        conversation_history: list[dict[str, str]] | None,
    ) -> tuple[str, str]:
        """Fix 2 — Option C (`_archive/plans/fix_design_exhaustion_bug037.md`
        §3, ADR-030 Decisions 1/2). On retry-budget exhaustion with a
        still-held empathy-degradable violation, deterministically
        substitutes (`near_dup_*` / `exact_repeat`) or prepends
        (`presence_missing`) ONE pool phrase as the leading empathy
        clause. Returns `(degraded_response, substituted_phrase)`.

        Hard constraint (REV-034 splice condition, binding): everything
        from the original leading clause's terminal punctuation onward
        ships BYTE-IDENTICAL to the model's last candidate — only the
        span before that point is ever touched, via index-precision
        string splicing (`_splice_point`), never a second LLM call, never
        question/clinical content.

        - `presence_missing`: by definition no leading clause was
          detected on this candidate (that IS the violation) — always
          PREPEND.
        - `near_dup_*` / `exact_repeat` / `self_referential_relief`:
          REPLACE the leading-clause span, but ONLY if that span itself
          reads as empathy content per `_is_empathy_clause` (CVR-014
          finding CF1 fix, `docs/ai/
          fix_design_exhaustion_bug037.md` §3 — a comma-joined response
          with TWO questions, the first terminated by its own `.` before
          a second, later `?`, gives `_splice_point` a valid index whose
          span is the first CLINICAL question, not an empathy clause;
          replacing it would silently delete clinical content, which the
          hard constraint above forbids). If no splice point exists, OR a
          splice point exists but its span fails the empathy test, PREPEND
          instead — never corrupts content, and still breaks the
          byte-identical repetition (`exact_repeat`'s own requirement:
          prepending new leading text changes the shipped string even
          though the original candidate's content is untouched). The
          no-splice-point fail-safe was already exercised by two real
          single-question artifacts (comma-joined, only `?` — no `.`/`!`
          anywhere); the empathy-test gate additionally covers the
          two-question shape where a splice point exists but is not safe
          to use."""
        phrase = DialogueAgent._select_degrade_phrase(conversation_history)
        if violation != "presence_missing":
            end = DialogueAgent._splice_point(assistant_response)
            if end is not None:
                leading_span = DialogueAgent._extract_leading_clause(assistant_response)
                # `leading_prefix_repeat`'s own definition already IS "this
                # leading clause is a byte-identical repeat" — no need for
                # (and no reliance on) the marker-based `_is_empathy_clause`
                # test other violation types require before a safe REPLACE.
                if (
                    violation == "leading_prefix_repeat"
                    or DialogueAgent._is_empathy_clause(leading_span)
                ):
                    return phrase + assistant_response[end:], phrase
        return f"{phrase}. {assistant_response}", phrase

    # CVR-057's 6-type discriminant table, condensed to short internal
    # labels for the telemetry log field only (never patient-facing, never
    # used to gate a response — see `_classify_utterance_type`'s own
    # docstring for the full mapping and its honest accuracy caveat).
    _UTTERANCE_TYPE_CRISIS = "crisis"
    _UTTERANCE_TYPE_META = "meta_utterance"
    _UTTERANCE_TYPE_SHORT_ANSWER = "short_answer"
    _UTTERANCE_TYPE_FACT_RESPONSE = "fact_response"
    _UTTERANCE_TYPE_EMOTION_DISCLOSURE = "emotion_disclosure"
    _SHORT_ANSWER_MAX_LEN = 6

    @staticmethod
    def _classify_utterance_type(patient_message: str, crisis_adjacent: bool) -> str:
        """CVR-057 qa recommendation #3 (`discussion.md`, 2026-07-25):
        best-effort classification of `patient_message` into ONE of
        CVR-057's 6-type discriminant table, using signals already
        computed elsewhere in this module/pipeline (no new LLM call, no
        new heuristic beyond what already exists). Honest scope
        disclosure: this collapses CVR-057's own types 5 ("민감/취약
        공개") into `emotion_disclosure` (no reliable code-level signal
        distinguishes "trauma/dependence disclosure" from ordinary
        emotional disclosure without a dedicated classifier this mission
        does not add) — logged for future live-data audit, not treated as
        a precise ground truth. Priority order mirrors the table's own
        severity ordering (crisis > meta > short > fact > emotion, the
        most specific/highest-stakes signal wins when several could
        apply)."""
        text = (patient_message or "").strip()
        if not text:
            return DialogueAgent._UTTERANCE_TYPE_SHORT_ANSWER
        if crisis_adjacent:
            return DialogueAgent._UTTERANCE_TYPE_CRISIS
        if is_meta_utterance(text):
            return DialogueAgent._UTTERANCE_TYPE_META
        if len(text) <= DialogueAgent._SHORT_ANSWER_MAX_LEN:
            return DialogueAgent._UTTERANCE_TYPE_SHORT_ANSWER
        if not any(m in text for m in _EMPATHY_MARKERS) and not any(
            w in text for w in ("힘들", "우울", "불안", "무섭", "지치", "슬프", "괴로")
        ):
            return DialogueAgent._UTTERANCE_TYPE_FACT_RESPONSE
        return DialogueAgent._UTTERANCE_TYPE_EMOTION_DISCLOSURE

    @staticmethod
    def _is_crisis_adjacent_turn(inp: DialogueInput) -> bool:
        """BUG-035 'crisis-adjacent turn' definition — reuses only runtime
        signals already threaded onto `DialogueInput` by `f1.py`; zero new
        classifier call, zero persona/ground-truth read.

        1. `session_state["probe_instruction"]` truthy: the SI safety-probe
           state machine or the mandatory end-of-session SI screen is
           driving this turn.
        2. `session_state["probe_just_concluded"]` truthy (ADR-029
           Decision 3 / design §8 de-escalation-turn boundary, rubric
           §10.3 ruling): the probe/de-escalation-CONCLUDING turn — the
           highest-need moment for empathic bridging, per CVR-011 Finding
           4. Threaded from `f1.py`'s own pre-existing `probe_just_concluded`
           local (set when the probe state machine's "deescalate" outcome
           or stage-exhaustion fires, `f1.py` Step 1b) into the EXISTING
           `session_state` field at the round-robin branch's construction
           site — no new `DialogueInput` field, no new business logic, only
           the already-computed flag threaded through the already-licensed
           unconstrained `session_state: dict[str, Any]` field (schema
           docstring), the same mechanism `prior_missing_slots` already
           uses. Structurally guarantees coverage of THIS turn independent
           of its own recomputed CTRS (CVR-011 binding condition 1) — the
           wider post-de-escalation sentiment population (later turns) is
           NOT runtime-enforceable (sentiment computed after the dialogue
           call) and is measured in EXP-018 instead (ADR-029 Decision 3).
        3. `safety_result["risk_level"] in {"medium","high"}` — this
           turn's own just-computed safety verdict. "critical"/CTRS 1-2
           never reaches here (crisis turns are intercepted before
           `DialogueAgent.run` is called)."""
        if inp.session_state and inp.session_state.get("probe_instruction"):
            return True
        if inp.session_state and inp.session_state.get("probe_just_concluded"):
            return True
        if inp.safety_result and inp.safety_result.get("risk_level") in ("medium", "high"):
            return True
        return False

    @staticmethod
    def _output_isolation_violation(
        assistant_response: str,
        filled_slots: dict[str, str],
        slot_updates_this_turn: dict[str, str] | None,
        patient_message: str,
    ) -> str | None:
        """BUG-037 (`_archive/plans/fix_design_exhaustion_bug037.md` §2,
        PLAN-2026-W28-U): patient-facing `assistant_response` must never
        ship clinical-note-register text or a mechanical echo. Checks, in
        priority order:

        1. Any `slot_updates_this_turn` value (slots written THIS turn,
           BEFORE this dialogue call — the confirmed BUG-037 trigger
           shape: `f1.py` Step 1b composes `risk_assessment` before the
           Step 3 dialogue call, and `_build_slot_context`'s "이미 수집
           완료" block renders it into the SAME turn's prompt, which the
           model then echoed verbatim). Reason: `"this_turn"`.
        2. Any other already-filled `filled_slots` value (a slot value
           composed in an EARLIER turn, still present in the accumulated
           slot state and therefore still renderable into this turn's
           prompt). Reason: `"prior_turn"`.
        3. The patient's own current-turn utterance, verbatim (CVR-012
           F2's sibling channel, observed at `VP-010_20260712_141728`
           turn 7 — a second, structurally distinct broken-generation at
           the same SI-screen-result pivot: the model echoes the
           patient's OWN words back instead of generating a reply). Same
           containment/equality mechanism, reused rather than duplicated
           — see the fix design note §2 "shared mechanism" assessment.
           Reason: `"patient_echo"`.

        Containment (`value in response`), not just equality, is checked
        so a partial echo embedded in an otherwise-fine response is also
        caught. `_MIN_OUTPUT_ISOLATION_LEN` gates every branch against
        coincidental short-string collisions (e.g. a 2-3 char slot value,
        or a short "네"/"아니요" patient reply a legitimate response
        might independently also contain)."""
        response = assistant_response.strip()
        if not response:
            return None

        def _matches(value: str | None) -> bool:
            if not value:
                return False
            v = value.strip()
            if len(v) < _MIN_OUTPUT_ISOLATION_LEN:
                return False
            return v == response or v in response

        for v in (slot_updates_this_turn or {}).values():
            if _matches(v):
                return "this_turn"
        for v in filled_slots.values():
            if _matches(v):
                return "prior_turn"
        if _matches(patient_message):
            return "patient_echo"
        return None

    @staticmethod
    def _internal_leak_violation(assistant_response: str) -> bool:
        """Coordinator directive (2026-07-25, role-separation principle,
        BUG-084b follow-on): the patient-facing `assistant_response` must
        never expose slot-layer internal machinery — a raw `SLOT_KEY`
        English identifier (e.g. "risk_assessment") or the internal terms
        "슬롯"/"coverage"/"grounding" — regardless of source. BUG-084b
        closed the ROOT CAUSE (this module's own prompt-injection sites no
        longer hand the model raw identifiers to copy); this is a
        defense-in-depth OUTPUT-level guard for the residual case of the
        model spontaneously generating one anyway, mirroring `_output_
        isolation_violation`'s own "must never ship" severity."""
        if not assistant_response:
            return False
        if any(key in assistant_response for key in _ALL_SLOTS):
            return True
        return any(term in assistant_response for term in ("슬롯", "coverage", "grounding"))

    @staticmethod
    def _build_retry_hint(
        violation: str, inp: DialogueInput, candidate_clause: str,
        target_slot: str | None = None,
    ) -> str:
        """Runtime hint injected into the per-call user_message (code, not
        a prompt-file edit — same mechanism as the pre-existing
        exact-repeat hint)."""
        deferred_slots = set((inp.session_state or {}).get("deferred_slots") or [])
        if violation == "question_missing":
            # User directive (2026-07-25): slot-based guided questioning is
            # a non-negotiable core function — a response must never end
            # without a follow-up question while slots remain uncollected.
            guide = _SLOT_QUESTION_GUIDE.get(target_slot or "", "")
            return (
                "\n\n[주의: 방금 응답에 질문이 전혀 없습니다. 공감 표현만으로 "
                "끝내지 말고, 반드시 다음 주제에 대한 질문 1개로 마무리하세요 — "
                f"{guide}]"
            )
        if violation == "risk_compound_question":
            return (
                "\n\n[주의: 지금은 위기(자살/자해) 선별 질문 턴입니다. 한 턴에 "
                "질문을 2개 이상 하지 마세요 — 최근 스스로를 해치고 싶거나 죽고 "
                "싶다는 생각이 든 적이 있는지, 그 한 가지만 부드럽게 질문하세요. "
                "다른 주제(타해 충동 포함)는 이번 턴에 함께 묻지 마세요.]"
            )
        if violation == "risk_question_missing":
            # BUG-082: mirrors `question_missing`'s hint, scoped to the
            # active SI-screen turn — the candidate must still ask the SI
            # question even after a meta-complaint/off-topic reply, not
            # pivot away from it with zero questions.
            return (
                "\n\n[주의: 지금은 위기(자살/자해) 선별 질문 턴인데 방금 응답에 "
                "질문이 전혀 없습니다. 공감 표현만으로 끝내지 말고, 반드시 최근 "
                "스스로를 해치고 싶거나 죽고 싶다는 생각이 든 적이 있는지 부드럽게 "
                "한 가지만 질문하세요.]"
            )
        if violation == "probe_topic_mismatch":
            # BUG-085-follow-up (session `04cfe927`): recompute the
            # expected stage the same way `run()`'s own precondition does
            # (`probe_instruction`'s text already literally embeds the
            # stage's hint) — no new parameter threaded, keeps this
            # method's existing signature.
            probe_instruction_text = (inp.session_state or {}).get("probe_instruction")
            expected_stage = (
                infer_literal_probe_stage(str(probe_instruction_text))
                if probe_instruction_text else None
            )
            hint = _PROBE_STAGE_HINTS.get(expected_stage or "", "")
            return (
                "\n\n[주의: 지금은 안전 탐색(Safety Probe) 단계입니다. 방금 응답의 "
                "질문이 이번 단계에 지정된 주제와 다릅니다. 다른 주제로 질문을 "
                f"바꾸지 말고, 반드시 다음 주제 하나만 부드럽게 질문하세요 — {hint}.]"
            )
        if violation == "target_mismatch":
            # BUG-077 item (A) safety net — only reached on a REPEAT
            # catch-all (see `catchall_violation`'s own gating comment in
            # `run()`), so the hint names that explicitly rather than
            # implying this is a first-occurrence rule.
            guide = _SLOT_QUESTION_GUIDE.get(target_slot or "", "")
            return (
                "\n\n[주의: 방금 응답이 이전에 이미 사용한 것과 같은, 특정 주제 없는 "
                '막연한 범용 질문입니다(예: "혹시 다른 증상이나 걱정되는 부분이 '
                '있으신가요?" 류). 같은 막연한 질문을 또 반복하지 말고, 이번 턴은 '
                f"반드시 다음 주제를 구체적으로 반영한 질문을 하세요 — {guide}]"
            )
        if violation == "exact_repeat":
            # BUG-084b: was `", ".join(missing)` (raw English SLOT_KEY
            # identifiers, e.g. "risk_assessment, personal_social_history")
            # injected with no "internal-only" instruction — live session
            # `94f75e81` shows the model echoed this raw list verbatim to
            # the patient. Now rendered via `_topic_list` (natural-language
            # Korean topic labels, never the raw key) plus an explicit
            # echo-prohibition, mirroring `_build_opening_context`'s
            # existing internal-term ban.
            missing = DialogueAgent.missing_questionable_slots(
                inp.filled_slots, deferred_slots=deferred_slots
            )
            missing_text = _topic_list(missing) if missing else "안전 확인"
            return (
                f"\n\n[주의: 이전과 동일한 응답입니다. 반드시 다른 질문을 하세요. "
                f"아직 다루지 않은 주제: {missing_text}. (이 목록은 내부 참고용입니다 — "
                "슬롯 이름이나 영어 식별자, \"슬롯\"이라는 단어 자체를 환자에게 그대로 "
                "언급하지 마세요.)]"
            )
        if violation == "self_referential_relief":
            # CVR-039 finding 5 / PLAN-2026-W30 cluster B #2.
            return (
                "\n\n[주의: 방금 응답이 상담자 자신의 안도·감정을 1인칭으로 표현했습니다"
                '("다행이에요"/"다행입니다"/"다행이네요" 계열 — "다행" 어근 사용 금지). '
                "상담자 자신의 감정을 진술하지 말고, 환자가 말한 사실 자체를 향한 짧은 "
                '사실-지향 인정으로 바꾸세요(예: "그런 변화가 있었군요"). 환자를 향한 '
                '"감사해요"/"감사합니다" 표현은 허용되며 금지 대상이 아닙니다.]'
            )
        if violation.startswith("near_dup"):
            return (
                f'\n\n[주의: 방금 응답의 공감 표현("{candidate_clause}")이 이전 턴과 '
                "거의 같은 표현입니다. 완전히 다른 표현으로, 환자가 방금 한 말에 맞춰 "
                "새로 공감하세요. 같은 문구나 비슷한 문구를 반복하지 마세요.]"
            )
        if violation == "leading_prefix_repeat":
            return (
                f'\n\n[주의: 방금 응답의 도입부("{candidate_clause}")가 최근 두 턴과 '
                "완전히 동일한 문구입니다. 반드시 처음부터 다른 표현으로 시작하세요 "
                "— 내용이 비슷하더라도 표현 자체를 새로 만드세요.]"
            )
        if violation.startswith("question_repeat"):
            # BUG-048 Finding (b). BUG-084b: same raw-key-echo fix as
            # `exact_repeat` above — natural-language topic list +
            # explicit echo-prohibition instead of raw `SLOT_KEY` names.
            missing = DialogueAgent.missing_questionable_slots(
                inp.filled_slots, deferred_slots=deferred_slots
            )
            missing_text = _topic_list(missing) if missing else "안전 확인"
            return (
                "\n\n[주의: 방금 응답의 질문 내용이 이전 턴의 질문과 거의 같습니다. "
                f"환자가 이미 답했거나 다른 미수집 주제({missing_text})에 대해 새로운 "
                "질문을 하세요. 같은 질문을 문구만 바꿔 반복하지 마세요. (위 목록은 내부 "
                "참고용입니다 — 슬롯 이름이나 영어 식별자를 그대로 언급하지 마세요.)]"
            )
        if violation == "presence_missing":
            return (
                "\n\n[주의: 지금은 위기 인접 상황입니다. 질문만으로 바로 시작하지 말고, "
                "반드시 공감하는 문장 1개로 먼저 시작한 뒤 질문하세요.]"
            )
        if violation.startswith("output_isolation"):
            if violation == "output_isolation_patient_echo":
                return (
                    "\n\n[주의: 방금 응답이 환자가 방금 한 말을 그대로 반복한 것입니다. "
                    "환자의 말을 그대로 따라 하지 말고, 환자에게 자연스럽게 응답하는 "
                    "AI 상담 도우미로서 새로 답하세요.]"
                )
            return (
                "\n\n[주의: 방금 응답이 내부 임상 기록(차트)에 쓰이는 문구를 그대로 "
                "포함하고 있습니다. 환자에게는 임상 기록 문구가 아니라 자연스러운 "
                "대화체로 응답하세요. 방금 응답을 그대로 반복하지 마세요.]"
            )
        if violation == "internal_leak":
            # Coordinator directive (2026-07-25, role-separation
            # principle) — defense-in-depth hint for the residual case of
            # the model spontaneously generating a raw slot-key/internal
            # term (BUG-084b's own ROOT-CAUSE fix already stopped this
            # module from ever injecting one).
            return (
                "\n\n[주의: 방금 응답에 슬롯 이름 같은 내부 시스템 식별자(영어 코드명) "
                "또는 \"슬롯\"/\"coverage\"/\"grounding\" 같은 내부 용어가 그대로 "
                "노출되었습니다. 그런 내부 식별자·용어를 절대 언급하지 말고, 환자에게 "
                "자연스러운 대화체로만 응답하세요.]"
            )
        return ""

    @staticmethod
    def _build_opening_context(session_state: dict[str, Any]) -> str:
        """Dialogue v3 (a): autonomous turn-0 greeting context.

        session_state keys — ALL carry-channel-licensed (AVC-02,
        `_archive/plans/validation_plan_f1f2_continuous.md` §6):
          - is_revisit: bool
          - carry_summary: str | None — F1Pipeline._summarize_prior_handoff's
            output, itself built ONLY from the narrowed final_slots+
            missing_slots carry content (`_compose_carry_content`); never
            raw risk_assessment/CTRS narrative.
          - prior_missing_slots: list[str] | None — slot KEY NAMES only, no
            values.

        No premature clinical content, no slot-machinery/internal-jargon
        language at turn 0 (plan §6 greeting-v3 validation check #2).
        """
        is_revisit = bool(session_state.get("is_revisit"))
        carry_summary = session_state.get("carry_summary")
        prior_missing = session_state.get("prior_missing_slots") or []

        lines = [
            "=" * 50,
            "아래 지시를 반드시 따르세요. (세션 시작 — 첫 인사)",
            "=" * 50,
            "",
            "## 이번 턴: 첫 인사",
            "- 한국어로 따뜻하게 첫 인사를 작성하세요.",
            "- 정신건강 사전문진을 돕는 AI 상담 도우미임을 밝히세요.",
            "- 실제 의사와의 대화가 아니며 편하게 이야기해도 된다고 안내하세요.",
            "- 아직 슬롯 문진/진단/위험 평가 등 임상적 내용을 언급하지 마세요.",
            "- \"슬롯\", \"coverage\", \"grounding\" 등 내부 시스템 용어를 언급하지 마세요.",
        ]
        if is_revisit:
            lines.append(
                "- 이 환자는 이전에 상담한 적이 있습니다. 이전 세션이 있었다는 "
                "사실은 자연스럽게 언급해도 좋습니다(예: \"지난번에 이어서...\")."
            )
            if carry_summary:
                lines.append(f"- 참고 가능한 이전 세션 정보: {carry_summary}")
            lines.append(
                "- 위 정보 이외의 세부사항(구체적 위험 서술, 진단 등)은 추측하거나 "
                "언급하지 마세요."
            )
            if prior_missing:
                # BUG-084b sweep: was a raw `SLOT_KEY` join — this whole
                # block already sits under the "내부 시스템 용어를 언급하지
                # 마세요" instruction above, but the raw English identifiers
                # themselves are a separate leak channel (same class as the
                # exact_repeat/question_repeat hints) — rendered via
                # `_topic_list` for consistency.
                lines.append(
                    "- 아래는 이전 세션에서 다루지 못한 항목입니다 — 오늘 대화에서 "
                    f"자연스럽게 이어서 다룰 수 있습니다: {_topic_list(prior_missing)}"
                )
            lines.append(
                "- 오늘 상태가 지난번과 비교해 어떤지 편하게 여쭤보며 대화를 여세요."
            )
        else:
            lines.append(
                "- 오늘 가장 도움받고 싶은 문제나 증상이 무엇인지 자연스럽게 한 번만 "
                "질문하며 마무리하세요."
            )
        lines.append("")
        return "\n\n" + "\n".join(lines)

    @staticmethod
    def _build_probe_context(probe_instruction: str) -> str:
        """Directive context for safety-probe turns — round-robin suspended."""
        lines = [
            "=" * 50,
            "아래 지시를 반드시 따르세요. (안전 탐색 모드)",
            "=" * 50,
            "",
            "## 이번 턴: 안전 탐색 — 슬롯 문진 중단",
            probe_instruction,
            "",
            "## 형식 규칙",
            "- 따뜻한 공감 1문장 + 위에 지시된 질문 **한 개**만.",
            "- 다른 문진 주제(수면, 가족력, 음주 등)를 질문하지 마세요.",
            "- 환자를 판단하거나 설교하지 마세요.",
            "",
        ]
        return "\n\n" + "\n".join(lines)

    def _build_slot_context(
        self,
        filled_slots: dict[str, str],
        session_state: dict[str, Any] | None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Build directive context for this turn's response generation.

        LLM이 반드시 따라야 하는 지시를 생성한다:
        - 이미 수집된 슬롯의 KEY+VALUE를 보여줘서 재질문 방지
        - 미수집 슬롯 중 이번 턴 타겟을 명시
        - 응답 형식 규칙 강제

        session_state["probe_instruction"]이 있으면 안전 탐색 모드 —
        round-robin 슬롯 타겟팅을 중단하고 probe 지시만 전달한다.
        session_state["opening_turn"]이 있으면 turn 0 자율 인사 모드 —
        (Dialogue v3, PLAN-2026-W28-Q W2).

        BUG-056 union (dialogue-steering ONLY): `filled_slots` as received
        here is the raw CALLER-supplied map (`routes/chat.py`'s
        `body.filled_slots`, the backend-accumulated slot state) — it can
        lag behind `state.slot_data`, which the orchestrator additively
        seeds/updates THIS turn (`OrchestratorAgent._seed_slot_data_from_
        caller`/`update_slots`, `agents/orchestrator.py:780-794`) but never
        threads back into `filled_slots` itself before calling this agent.
        Steering (this method's target-slot selection + "already collected"
        display) unions the two (`filled_slots ∪ state.slot_data`, caller
        value wins on conflict) so a slot the orchestrator already knows is
        filled is not re-asked. Scope is deliberately narrow: this union is
        used ONLY inside `_build_slot_context` (steering context) — the
        safety path, coverage computation, handoff assembly, and the
        backstop gate all continue to read `state.slot_data`/`filled_slots`
        directly, unaffected by this method.
        """
        if session_state and session_state.get("opening_turn"):
            return self._build_opening_context(session_state)

        if session_state and session_state.get("probe_instruction"):
            return self._build_probe_context(str(session_state["probe_instruction"]))

        prior_missing_slots = set((session_state or {}).get("prior_missing_slots") or [])
        # Cluster A (asked-slot generalized fix, additive): slots the
        # orchestrator has deferred after repeated unanswered asks —
        # threaded through the same unconstrained `session_state` dict
        # `prior_missing_slots`/`probe_instruction` already use, so this
        # agent needs no orchestrator-specific import.
        deferred_slots = set((session_state or {}).get("deferred_slots") or [])

        # BUG-056: union the orchestrator's additive `state.slot_data`
        # (nested in `session_state`, the SAME unconstrained dict already
        # read above) into the raw caller `filled_slots` — steering-only,
        # see docstring above.
        orchestrator_slot_data = (session_state or {}).get("slot_data") or {}
        filled_slots = {**orchestrator_slot_data, **filled_slots}

        filled_with_values = {k: v for k, v in filled_slots.items() if v and k in _ALL_SLOTS}

        all_missing = self.missing_questionable_slots(filled_slots, deferred_slots=deferred_slots)

        lines: list[str] = []

        # ── 1. 절대 규칙 ──
        lines.append("=" * 50)
        lines.append("아래 지시를 반드시 따르세요.")
        lines.append("=" * 50)
        lines.append("")

        # ── 2. 공감 표현 반복 금지 ──
        # BUG-030 iter-2: shared, uncapped extraction (was inlined here with
        # a `[:30]` cap — `_extract_used_empathy_clauses` has none).
        # BUG-036 fix: the shared extraction now returns EVERY occurrence
        # (no dedup — needed by the retry guard below). For this SHOWN
        # prompt hint, dedupe locally (order-preserving) so the X-list
        # still surfaces up to 5 DISTINCT previously-used phrases rather
        # than one repeated phrase shown 5 times — unchanged soft-nudge
        # intent, just moved from the shared extractor to this call site.
        used_empathy_all: list[str] = self._extract_used_empathy_clauses(conversation_history)
        seen_empathy: set[str] = set()
        used_empathy: list[str] = []
        for clause in used_empathy_all:
            if clause not in seen_empathy:
                seen_empathy.add(clause)
                used_empathy.append(clause)

        lines.append("## 공감 표현 규칙")
        lines.append("- 공감은 1문장으로 끝내고, 바로 새 질문을 하세요. 공감 문장을 생략하지 마세요.")  # noqa: E501
        lines.append("- 환자 말을 장황하게 반복하지 마세요.")
        lines.append("- 정해진 문구를 고르지 말고, 환자가 방금 한 말의 내용과 감정에 맞춰 그때그때 새로 표현하세요.")  # noqa: E501
        # 4연속 verbatim 도입부 반복 (2026-07-25, 라이브 재검증): "지칠 수
        # 있어요"류 문구가 `_EMPATHY_MARKERS` 표면형과 불일치해 근접중복
        # 가드가 미발동, 아래 X-list("이미 사용했으므로 절대 다시 사용하지
        # 마세요")가 이미 보여주고 있었음에도 4턴 연속 그대로 반복 출고됨.
        # 1순위 대응(사용자 반-강제 원칙): 상태 가시화를 "직전 턴 도입부"로
        # 좁혀 더 눈에 띄게 별도 강조 + 다양화 원칙 1문장 추가. 하드 가드
        # (`_leading_prefix_repeat_violation`, run()의 최후 안전망)는 이
        # 프롬프트 대응이 불충분할 때만 작동한다.
        if used_empathy:
            lines.append(
                f'- **직전 턴 도입부**: "{used_empathy[-1]}..." — 이번 턴은 '
                "반드시 다른 표현으로 시작하세요."
            )
            lines.append("- 아래 표현은 이전 턴에서 이미 사용했으므로 **절대 다시 사용하지 마세요**:")  # noqa: E501
            for e in used_empathy[-5:]:
                lines.append(f'  X "{e}..."')
            lines.append(
                "- 매 턴 도입부(첫 문장)를 이전 턴들과 다르게 새로 표현하는 "
                "것이 원칙입니다 — 내용은 비슷하더라도 표현은 매번 바꾸세요."
            )
        lines.append("")

        # ── 3. 이미 수집된 정보 (BUG-077 state-visibility: filled/denied 구분) ──
        # 사용자 지시(2026-07-25): "단편적인 예시에 기능을 강제시키지 말 것" —
        # 이 절이 BUG-077 item (A)의 1순위 해법이다. `slot_status`
        # (`SessionState.slot_status`, `routes/chat.py`가 `state.model_dump()`
        # 로 그대로 threading — f1.py 등 이 키를 채우지 않는 caller는 아래가
        # 조용히 no-op) 를 읽어 "수집됨"과 "환자 부인(denied)"을 명시적으로
        # 분리해 보여준다 — 모델이 "이미 부인된 항목은 다시 묻지 않는다"는
        # 원칙을 스스로 지킬 수 있도록 상태를 보여주는 것이 1순위이며, 아래
        # `run()`의 target-binding 재시도/강등 가드는 이 방식이 실측
        # (라이브 재검증)에서 불충분할 때만 작동하는 안전망이다(그 가드 자체의
        # 트리거 조건도 "이미 한 번 범용 질문이 있었던 경우"로 좁혀져 있다 —
        # 첫 시도는 하드 개입 없이 통과된다).
        # Coordinator directive (2026-07-25, "수집-불가 응답의 즉시-이동
        # 규칙"): `slot_status` now carries a THIRD value, "unknown" (see
        # `OrchestratorAgent._update_asked_slot_tracking`) — a "잘
        # 모르겠습니다"-class reply is clinically distinct from an active
        # "denied" and must be shown/handled distinctly here too, not
        # silently folded into either "이미 수집 완료" (implies substantive
        # positive content) or "denied" (implies an active denial).
        slot_status_map: dict[str, str] = (session_state or {}).get("slot_status") or {}
        if filled_with_values:
            denied_items = {
                k: v for k, v in filled_with_values.items()
                if slot_status_map.get(k) == "denied"
            }
            unknown_items = {
                k: v for k, v in filled_with_values.items()
                if slot_status_map.get(k) == "unknown"
            }
            positive_items = {
                k: v for k, v in filled_with_values.items()
                if k not in denied_items and k not in unknown_items
            }
            if positive_items or denied_items or unknown_items:
                # BUG-084b sweep: item labels below now render via
                # `_topic_label` (natural-language, never a raw `SLOT_KEY`)
                # + an explicit echo-prohibition, same discipline as the
                # exact_repeat/question_repeat hints and the opening/prior-
                # missing lists above.
                lines.append(
                    "- 아래 목록들의 항목명은 내부 분류용 라벨입니다 — 환자에게 "
                    "그대로 인용하지 말고, 자연스러운 표현으로 이미 아는 내용을 "
                    "반영하세요."
                )
            if positive_items:
                lines.append("## 이미 수집 완료 — 다시 질문 금지")
                for k, v in positive_items.items():
                    display_val = v if len(v) <= 80 else v[:80] + "..."
                    lines.append(f"  - {_topic_label(k)}: {display_val}")
                lines.append("")
            if denied_items:
                lines.append("## 환자가 이미 부인(denied)함 — 다시 묻지 않음")
                for k, v in denied_items.items():
                    display_val = v if len(v) <= 80 else v[:80] + "..."
                    lines.append(f"  - {_topic_label(k)}: {display_val}")
                lines.append("")
            if unknown_items:
                lines.append(
                    "## 환자가 모른다고 답함(unknown) — 다시 캐묻지 않음"
                )
                for k, v in unknown_items.items():
                    display_val = v if len(v) <= 80 else v[:80] + "..."
                    lines.append(f"  - {_topic_label(k)}: {display_val}")
                lines.append(
                    "- 위 항목에 대해서는 캐묻거나 재확인 질문을 하지 마세요. "
                    "짧게 \"알겠습니다\" 류로 인정한 뒤 곧바로 다음 미수집 주제로 "
                    "넘어가세요."
                )
                lines.append("")

        # ── 3b. 질문-응답 이력 (BUG-077 state-visibility) ──
        # 실제 렌더된 질문 텍스트에서 어떤 주제를 물었는지 역추론
        # (`infer_literal_target_slot` — BUG-077 item (B)의 어석 귀속 로직과
        # 동일한 정의를 공유, `src.grounding`) 해, 이번 세션에서 이미 어떤
        # 주제로 물었고 환자가 뭐라 답했는지를 보여준다. 특정 주제로 귀속되지
        # 않는 질문(막연한 범용 질문)도 "(특정 주제 없는 범용 질문)"으로
        # 그대로 노출해, 모델이 "나는 이미 한 번 막연하게 물었다"는 사실을
        # 스스로 인지하고 이번 턴에는 구체적 주제를 택하도록 유도한다 — 새
        # 규칙을 강제하는 대신 사실을 보여주는 방식.
        qa_history = self._build_asked_topic_history(conversation_history)
        if qa_history:
            lines.append("## 지금까지 질문-응답 이력 (참고 — 이미 다룬 주제 파악용)")
            lines.extend(qa_history)
            lines.append(
                "- 위 이력에 특정 주제 없는 막연한 질문이 있었다면, 같은 막연한 "
                "질문을 또 반복하지 말고 이번 턴은 아래 지정된 구체적 주제로 "
                "질문하세요."
            )
            lines.append("")

        # ── 4. 이번 턴 행동 ──
        if all_missing:
            target = self.compute_target_slot(
                filled_slots, conversation_history, deferred_slots=deferred_slots
            )
            if target is None:  # defensive — all_missing non-empty implies a target
                target = all_missing[0]

            guide = _SLOT_QUESTION_GUIDE.get(target, target)
            # BUG-084b sweep: the section header previously interpolated
            # the raw `SLOT_KEY` identifier directly ("## 이번 턴:
            # risk_assessment에 대해 질문하세요") — now shows the
            # natural-language topic label; the actual instruction content
            # (`guide`) was already natural-language and is unchanged.
            lines.append(f"## 이번 턴: {_topic_label(target)}에 대해 질문하세요")
            lines.append(f"질문 방향: {guide}")
            lines.append(
                "- 위 제목/방향은 내부 참고용입니다 — 슬롯 이름이나 영어 식별자를 "
                "환자에게 그대로 언급하지 마세요."
            )
            # Dialogue v3 (b): continuity phrasing for slots missing from a
            # prior session (key names only — AVC-02, never values/prose).
            if target in prior_missing_slots:
                lines.append(
                    "연속성 안내: 이 항목은 지난 상담에서도 다루지 못한 부분입니다. "
                    "자연스럽게 이어서 질문하되, 필요하다면 지난 상담을 자연스럽게 "
                    "언급해도 좋습니다(예: \"지난번에 여쭤보지 못했는데...\")."
                )
            lines.append("")

            remaining = [s for s in all_missing if s != target]
            if remaining:
                # BUG-084b: raw `SLOT_KEY` join replaced with `_topic_list`
                # (see fix-direction note citing this exact line).
                lines.append(f"이후 미수집: {_topic_list(remaining)}")
                lines.append("")
        else:
            # ── 모든 슬롯 수집 완료 → 요약 모드 ──
            lines.append("## 모든 정보가 수집되었습니다 — 요약 모드")
            lines.append("새로운 질문을 하지 마세요. 아래와 같이 응답하세요:")
            lines.append('1. 지금까지 수집된 내용을 2-3문장으로 간략히 요약')
            lines.append('2. "틀린 부분이나 빠진 내용이 있으면 말씀해 주세요"로 마무리')
            lines.append("3. 절대 새로운 질문을 추가하지 마세요.")
            lines.append("")

        return "\n\n" + "\n".join(lines)

    @staticmethod
    def _parse_response(content: str) -> DialogueLLMResponse:
        """Parse LLM JSON response with fallback."""
        try:
            data = json.loads(content)
            return DialogueLLMResponse.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Dialogue JSON parse failed: %s", exc)
            # Try extracting from markdown code block
            stripped = content.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                end = len(lines)
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip() == "```":
                        end = i
                        break
                try:
                    data = json.loads("\n".join(lines[1:end]))
                    return DialogueLLMResponse.model_validate(data)
                except Exception:
                    pass

            return DialogueLLMResponse(
                assistant_response=content,
                reason_summary="JSON parse failed — raw response used",
            )

    @staticmethod
    def _get_previous_responses(history: list[dict[str, str]]) -> list[str]:
        """Get all previous assistant messages from conversation history."""
        return [msg["content"] for msg in history if msg.get("role") == "assistant"]
