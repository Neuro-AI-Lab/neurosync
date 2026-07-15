"""VP-004 longitudinal arc pack — `fluctuating_panic_recurrence` — brainstorm design deliverable.

Schema/location convention mirrors `tests/simulation/scenario_pack.py` (EXP-023 precedent). Not
yet wired into `_SCENARIO_PACKS` — pending critic REV + clinical-validator CVR, same gate pattern
`PLAN-2026-W29-D` applied to VP-001/003 (`ADR-036`). See `vp002_treatment_response_setback.py`'s
docstring for the shared `scenario_pack_id` wiring caveat (applies identically here).

Grounded in `docs/ai/personas/VP-004_revisit_severe.md` (read in full) — S1 of this arc reuses the
persona's own documented "current (재진)" state verbatim (§2/§3/§8: PHQ-9 ~21, GAD-7 ~16, CTRS 3,
panic attacks new at 1-2x/week since a documented 2026-05-10 ER visit, passive SI = fear-based
"이러다 죽을 것 같다" only, never active). Crisis content in this pack is licensed by the persona's
own documented profile (panic attacks, passive SI, intermittent self-harm impulse never acted on)
— never escalated beyond what the persona file already establishes; no new crisis category is
introduced (no active SI/plan is ever scripted, matching the persona's own "구체적 계획 없음").

Arc shape (per user directive): fluctuating course — a scripted panic-recurrence trigger mid-arc,
then partial (not full) stabilization by the end. The panic-recurrence trigger uses a
persona-plausible stressor class (a translation deadline / the ER-visit anniversary) — the same
categories the persona's own history already establishes as panic triggers
(`VP-004_revisit_severe.md` §7's "번역 작업 중" onset, and 마감 압박 already named in §2 원인).
"""

from __future__ import annotations

from tests.simulation.scenario_pack import ScenarioSession

DAY_OFFSETS: list[int] = [0, 7, 14, 21, 35, 49, 63, 91, 137, 183]


def _phase_for(session_index: int) -> str:
    if session_index <= 4:
        return "acute_engagement"
    if session_index <= 7:
        return "response_consolidation"
    return "maintenance"


_STATES: list[str] = [
    # S1 — day0, = persona's own documented "current (재진)" state, verbatim-grounded
    "2개월 전 우울증 치료 시작 이후 약물을 두 번 바꿨음에도 악화 추세이며, 한 달 전부터 "
    "공황 발작이 새로 생겼습니다(주 1-2회, 한 달 전 응급실 방문 이력). 심한 우울감이 "
    "하루 대부분 지속되고, 수면은 3-4시간, 식욕은 하루 1끼 간신히. 수동적 자살 사고("
    "\"이러다 정말 죽을 것 같다\")는 있으나 구체적 계획은 없습니다.",
    # S2 — modest stabilization begins (med adjustment discussed at S1)
    "Alprazolam PRN 복용 패턴을 조정한 이후 공황 발작 빈도가 주 1회로 소폭 줄었습니다. "
    "우울감은 여전히 심하지만 조금은 나아진 느낌이 있습니다.",
    # S3
    "기분이 아주 조금씩 나아지고 있습니다. 수면이 4시간 정도로 소폭 늘었습니다.",
    # S4
    "조심스럽게 호전이 이어지고 있습니다. 번역 작업을 하루 30분 정도라도 시도해보고 "
    "있습니다.",
    # S5 — consolidation, cautious improvement continues
    "지난 2주간 공황 발작이 한 번도 없었습니다. 우울감도 조금씩 옅어지는 느낌이고, 희망을 "
    "조금씩 느끼기 시작했습니다.",
    # S6 — panic-recurrence trigger
    "번역 마감이 다시 몰리면서, 공교롭게도 응급실 방문 1주기와 겹쳐 다시 심한 공황 발작이 "
    "왔습니다. 예기불안도 그만큼 다시 심해졌습니다.",
    # S7 — fluctuation peak
    "이번 주에 공황 발작이 두 번 더 있었고, 다시 마감을 놓쳤습니다. 수동적 자살 사고("
    "\"이러다 죽을 것 같다\")가 다시 매일 수준으로 심해졌지만, 여전히 구체적 계획은 "
    "없습니다.",
    # S8 — maintenance begins, partial stabilization begins
    "주치의가 짧은 호흡 이완 기법과 인지행동 상담 연계를 제안했고, 시도해본 이후 공황 "
    "발작 빈도가 다시 줄기 시작했습니다.",
    # S9
    "공황 발작이 한 달에 한 번 정도로 줄었습니다. 번역 작업도 부분적으로 재개했습니다. "
    "여전히 완전히 편해진 것은 아닙니다.",
    # S10 — final, partial stabilization (not full remission)
    "6개월 전보다는 확실히 나아졌지만 완전히 회복된 것은 아닙니다. 공황에 대한 예기불안은 "
    "여전히 남아 있고, 수동적 자살 사고도 이제는 매일이 아니라 가끔 스치는 정도입니다.",
]

_EVENTS: list[list[str]] = [
    [],
    ["Alprazolam PRN 복용 패턴을 조정함(주치의 상의)"],
    ["특별한 사건 없이 조금씩 안정됨"],
    ["번역 작업을 하루 30분씩 시도해봄"],
    ["2주간 공황 발작 없이 지나감"],
    ["번역 마감이 다시 몰림", "응급실 방문 1주기와 겹침"],
    ["공황 발작이 이번 주 2회 발생함", "번역 마감을 다시 놓침"],
    ["호흡 이완 기법 시도 및 인지행동 상담 연계 시작"],
    ["번역 작업을 부분적으로 재개함"],
    ["큰 위기 없이 한 달을 보냄"],
]

_REVEALS: list[str] = [
    "심한 우울감과 공황 공포를 짧고 감정적인 어투로 표현하세요. 수동적 자살 사고를 물으면 "
    "숨기지 말고 \"이러다 죽을 것 같다\"는 공포로 드러내되, 구체적 계획은 없다고 명확히 "
    "답하세요.",
    "아주 작은 호전을 조심스럽게, 큰 기대 없이 이야기하세요.",
    "여전히 힘들다는 기조를 유지하되, 수면이 소폭 나아졌음을 담담하게 언급하세요.",
    "작은 시도(번역 30분)에 대해 자신 없는 톤으로, 그러나 완전히 포기하지는 않은 느낌으로 "
    "답하세요.",
    "지난 2주 공황이 없었다는 것을 조심스러운 희망과 함께 이야기하세요.",
    "다시 심해진 공황과 예기불안을 두려움 섞인 톤으로 표현하세요. 마감과 응급실 기억이 "
    "겹쳤다는 점을 자연스럽게 언급하세요.",
    "가장 힘든 재발 국면을 표현하세요. 수동적 자살 사고(\"이러다 죽을 것 같다\")가 다시 "
    "심해졌음을 분명히 드러내되, 구체적 계획은 여전히 없다고 명확하게 답하세요.",
    "새로 시도한 이완 기법이 도움이 됐다는 것을 담담하게, 약간의 안도감과 함께 이야기하세요.",
    "여전히 조심스럽지만 실질적인 호전(공황 빈도 감소, 작업 재개)을 이야기하세요.",
    "부분적이고 불완전한 회복을 표현하세요 — 예기불안이 완전히 사라진 것이 아니라 줄었을 "
    "뿐이고, 수동적 자살 사고도 빈도만 줄었을 뿐이라는 점을 명확히 하세요.",
]

_PHQ9_TARGETS = [
    "~21", "~19", "~18", "~16", "~15",
    "~19 (recurrence onset)", "~20 (arc peak)", "~17", "~15", "~14",
]
_GAD7_TARGETS = [
    "~16", "~15", "~14", "~13", "~11",
    "~15 (recurrence onset)", "~16 (arc peak)", "~13", "~11", "~10",
]
_CTRS_TARGETS = [
    "3", "3", "3", "3-4", "4",
    "2", "2",  # S6-S7: daily passive-SI escalation under probe — CVR-027 major
    "3-4", "4", "4",
]
_PANIC_TARGETS = [
    "1-2x/week", "1x/week", "1x/week", "0-1x/week", "0x (2wk clear)",
    "recurrence (1 severe episode)", "2x this week (peak)", "declining",
    "~1x/month", "rare, residual anticipatory anxiety",
]

assert len({
    len(_STATES), len(_EVENTS), len(_REVEALS), len(_PHQ9_TARGETS),
    len(_GAD7_TARGETS), len(_CTRS_TARGETS), len(_PANIC_TARGETS), len(DAY_OFFSETS),
}) == 1

VP_004_FLUCTUATING_PANIC_RECURRENCE: tuple[ScenarioSession, ...] = tuple(
    ScenarioSession(
        session_index=i + 1,
        day_offset=DAY_OFFSETS[i],
        arc_mode="fluctuating_panic_recurrence",
        phase_label=_phase_for(i + 1),
        state_descriptor_ko=_STATES[i],
        inter_session_events_ko=list(_EVENTS[i]),
        symptom_targets={
            "PHQ-9": _PHQ9_TARGETS[i],
            "GAD-7": _GAD7_TARGETS[i],
            "CTRS": _CTRS_TARGETS[i],
            "panic_frequency": _PANIC_TARGETS[i],
        },
        reveal_guidance_ko=_REVEALS[i],
    )
    for i in range(10)
)

# See vp002_treatment_response_setback.py docstring: `_ARC_MODE_TO_PERSONA` needs a
# "fluctuating_panic_recurrence" -> "VP-004" entry added at wiring time.
_ids = [
    f"VP-004_fluctuating_panic_recurrence_s{s.session_index:02d}"
    for s in VP_004_FLUCTUATING_PANIC_RECURRENCE
]
assert len(set(_ids)) == len(_ids), f"scenario_pack_id collision: {_ids}"
