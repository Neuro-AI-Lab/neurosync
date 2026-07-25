"""Safety Probe protocol — production port (ADR-042, EXP-030 cluster C).

Ported from `src.f1`'s harness-only 4-stage graduated Safety Probe state
machine (`_ProbeState`, `_PROBE_STAGES`, `_probe_should_trigger`,
`_process_probe_answer`, `_compose_probe_risk_assessment`,
`_compose_screen_risk_assessment`, `f1.py:106-169,849-910`) so
`risk_assessment` can be grounded on the production `/ai/chat/respond`
route (`OrchestratorAgent`), not only in the offline harness.

Pure functions only (no LLM, no I/O, no mutable module state) — same
"shared production/harness code" discipline `src.grounding` already
follows. `SessionState`'s `probe_*` fields (see `src.schemas.orchestrator`)
are the stateless-wire equivalent of `f1.py`'s in-process `_ProbeState`
dataclass; every function here operates on primitive values (str/int/
list/bool) passed in by the caller rather than on a dataclass instance,
so no new server-side session store is introduced (ADR-042 constraint).

`src/f1.py` is intentionally left untouched by this port (its own copy of
this logic keeps working unchanged, out of scope for this mission) —
this module is the NEW, production-facing home for the same logic, not a
refactor of the harness.
"""

from __future__ import annotations

import re

from src.grounding import reply_has_negation
from src.schemas.common import should_trigger_soft_safety

# Graduated probe stages: 사고 빈도 → 구체적 계획 → 수단/의도 → 보호 요인
# (verbatim port of f1.py's `_PROBE_STAGES`)
PROBE_STAGES: list[tuple[str, str]] = [
    ("frequency", "최근에 그런 생각이 얼마나 자주 드는지"),
    ("plan", "혹시 구체적인 계획을 생각해 본 적이 있는지"),
    ("means_intent", "혹시 방법이나 수단을 생각해 두었는지, 실행할 생각이 있는지"),
    ("protective", "그런 순간에 버틸 수 있게 해 주는 것(가족, 친구, 소중한 일 등)이 있는지"),
]

# Belt-and-braces lexical check for plan/means disclosure in probe answers
# (verbatim port of f1.py's `_PLAN_DISCLOSURE_MARKERS`).
_PLAN_DISCLOSURE_MARKERS = (
    "계획", "방법", "준비", "사놨", "사 놨", "사뒀", "사 뒀", "유서", "날짜",
    "수단", "정해뒀", "정해 뒀", "정했", "구해놨", "구해뒀", "모아뒀", "모아놨",
)

# ISS-043 (verbatim port): the negation veto must be clause-local, not
# sentence-global. Clauses are split on sentence punctuation and common
# contrastive connectives (는데/지만) so "계획을 세워뒀어요. 근데 아직
# 실행은 않았어요" still escalates: the disclosure clause is affirmative
# even though a later clause carries a negation morpheme.
_CLAUSE_SPLIT_RE = re.compile(r"[.!?…~\n,;]|(?:는데|지만)\s")

# Mandatory SI screen instruction (verbatim port of f1.py's
# `_SI_SCREEN_INSTRUCTION`) — used when all other question-able slots are
# collected but risk_assessment is still not grounded: the session may
# not terminate purely on slot-completion without ever asking about risk.
SI_SCREEN_INSTRUCTION = (
    "필요한 문진 정보는 대부분 수집되었습니다. 상담을 마무리하기 전에 안전 확인이 "
    "필요합니다. 공감 1문장 후, 최근에 스스로를 해치고 싶다거나 죽고 싶다는 생각이 "
    "든 적이 있는지 부드럽게 **한 가지만** 질문하세요. 다른 주제는 질문하지 마세요."
)


def clip(text: str, limit: int = 80) -> str:
    """Collapse whitespace and truncate `text` to `limit` chars (+ ellipsis)."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def has_plan_disclosure(text: str) -> bool:
    """Clause-local lexical check (ISS-043 port): some CLAUSE discloses a
    plan/means without a clause-local negation. Legitimate denials
    ("계획 같은 건 없어요") keep the marker and the negation in the same
    clause and do not escalate."""
    for clause in _CLAUSE_SPLIT_RE.split(text):
        if not clause or not clause.strip():
            continue
        if any(marker in clause for marker in _PLAN_DISCLOSURE_MARKERS):
            if not reply_has_negation(clause):
                return True
    return False


def probe_should_trigger(ctrs_level: int, categories: list[str] | set[str]) -> bool:
    """CTRS 3 + suicidal_ideation/self_harm category -> enter probe mode.
    Delegates to the shared predicate (`src.schemas.common.
    should_trigger_soft_safety`) — the SAME condition BUG-047's soft-safety
    note uses, never re-derived independently."""
    return should_trigger_soft_safety(ctrs_level, categories)


def build_probe_instruction(stage_idx: int) -> str:
    """Directive text for DialogueAgent's current probe stage."""
    stage_idx = min(stage_idx, len(PROBE_STAGES) - 1)
    _, question_hint = PROBE_STAGES[stage_idx]
    return (
        "환자가 자살/자해 관련 사고를 표현했습니다. 지금은 안전 탐색 단계입니다. "
        "따뜻한 공감 1문장을 먼저 말한 뒤, 아래 주제를 부드럽게 한 가지만 "
        f"질문하세요. 질문 주제: {question_hint}."
    )


# BUG-083 (BUG-079 parity, `_advance_safety_probe`'s literal-target check):
# topic-keyword sets per probe stage, sourced verbatim from `PROBE_STAGES`'
# own `question_hint` phrases (the exact text `build_probe_instruction`
# embeds into the rendered directive) — never independently invented, same
# discipline `src.grounding._SLOT_TOPIC_KEYWORDS` follows for the 8
# question-able slots. Deliberately narrow/false-negative-biased: an
# ambiguous rendering must infer NO stage rather than guess wrong.
_STAGE_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "frequency": ("얼마나 자주", "자주 드는", "자주 드시는"),
    "plan": ("구체적인 계획", "계획을 생각", "어떤 계획"),
    "means_intent": ("방법이나 수단", "수단을 생각", "실행할 생각", "실행할 의도"),
    "protective": ("버틸 수 있게", "가족, 친구", "소중한 일"),
}


def infer_literal_probe_stage(text: str) -> str | None:
    """BUG-083: infer which probe stage a rendered assistant question
    LITERALLY, recognizably asked about, via topic-keyword match against
    `_STAGE_TOPIC_KEYWORDS`. Returns None when no stage's keywords match
    (an ambiguous/topic-drifted rendering) — deliberately conservative, the
    same "no guess" discipline `src.grounding.infer_literal_target_slot`
    uses for the sibling 8-slot case.

    Pure, no I/O — used by `OrchestratorAgent._advance_safety_probe`'s
    `probe_active` branch to validate that the immediately-prior rendered
    text actually asked the CURRENT stage's topic before scoring a reply
    against it (BUG-079 parity)."""
    if not text:
        return None
    for stage, keywords in _STAGE_TOPIC_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return stage
    return None


def classify_probe_answer(stage_idx: int, patient_message: str) -> str:
    """Classify the answer to the previously asked probe question.

    Returns "escalate" | "deescalate" | "continue". `stage_idx` is the
    stage of the question that was JUST answered (not yet advanced). Pure
    classification only — callers own any state mutation (e.g. capturing
    the "protective" stage's answer, advancing `stage_idx`).

    BUG-083 (2026-07-25, qa live repro `b88d740e`): previously ONLY the
    "plan"/"means_intent" stages checked `reply_has_negation` — an
    unambiguous, explicit, full SI denial arriving at the "frequency"
    stage (stage 0, the first-asked stage) was silently discarded as
    "continue", advancing the probe past a denial it never captured. The
    denial-check is now stage-name-independent: ANY stage (except
    "protective", which already unconditionally de-escalates regardless
    of content) de-escalates on an explicit denial. This closes the gap
    without weakening the escalation check — `has_plan_disclosure` is
    still evaluated FIRST and unconditionally, so a plan/means disclosure
    still escalates even if it happens to also contain a negation
    morpheme elsewhere (e.g. "계획은 없는데 방법은 정해뒀어요").
    """
    answered_idx = min(stage_idx, len(PROBE_STAGES) - 1)
    stage_name = PROBE_STAGES[answered_idx][0]

    if has_plan_disclosure(patient_message):
        return "escalate"

    if stage_name == "protective":
        return "deescalate"
    if reply_has_negation(patient_message):
        return "deescalate"
    return "continue"


def compose_probe_risk_assessment(
    trigger_utterance: str,
    final_answer: str,
    protective_answer: str = "",
) -> str:
    """Compose risk_assessment from the ACTUAL probe exchange (no templates)."""
    parts = [f'자살/자해 사고 표현 있음 — 환자 발화: "{clip(trigger_utterance)}"']
    if final_answer and reply_has_negation(final_answer):
        parts.append(f'구체적 계획/의도 부인 — 환자 발화: "{clip(final_answer)}"')
    elif final_answer:
        parts.append(f'탐색 질문에 대한 환자 응답: "{clip(final_answer)}"')
    if protective_answer and protective_answer != final_answer:
        parts.append(f'보호 요인 — 환자 발화: "{clip(protective_answer)}"')
    return "; ".join(parts)


def compose_screen_risk_assessment(patient_message: str) -> str:
    """Compose risk_assessment from the mandatory SI screening answer
    (outside probe mode) — actual patient words, no templates."""
    if reply_has_negation(patient_message):
        return f'자살/자해 사고 탐색 질문에 부인 — 환자 발화: "{clip(patient_message)}"'
    return f'자살/자해 사고 탐색 질문에 대한 환자 응답: "{clip(patient_message)}"'
