"""VP-002 longitudinal arc pack — `treatment_response_setback` — brainstorm design deliverable.

Schema/location convention mirrors `tests/simulation/scenario_pack.py` (EXP-023 precedent,
`ScenarioSession` dataclass, `render_scenario_guideline` template, `scenario_pack_id` format) —
this file is NOT yet imported by `scenario_pack.py`'s `_SCENARIO_PACKS` dict; wiring it in is a
one-line developer change (`from .scenario_packs.vp002_treatment_response_setback import
VP_002_TREATMENT_RESPONSE_SETBACK` + a dict entry), pending critic/clinical-validator review of
this content (no ADR/CVR filed yet — this file is brainstorm's design proposal only, per the
`brainstorm` agent's out-of-implementation-scope charter; a critic REV + clinical-validator CVR
must review before any harness run, matching `PLAN-2026-W29-D`'s own gate pattern for VP-001/003).

Grounded in `docs/ai/personas/VP-002_revisit_mild.md` (read in full) — S1 of THIS arc reuses that
persona file's own "current (재진)" state verbatim (§2/§3/§7: PHQ-9 ~7, GAD-7 ~5, CTRS 5,
Escitalopram 10mg 6주째, 아내 지지, 산책/동료 관계 재개) as the arc's session 1, i.e. the 6-week
revisit already documented in the persona file becomes this pack's day-0 session; the pack then
extrapolates 9 further chained sessions across the following ~6 months (10 sessions total,
day_offset 0-183, all `[DESIGN INTENT]` beyond S1).

Arc shape (per user directive): gradual improvement with ONE scripted setback, mid-arc, then
recovery resuming — never crisis (VP-002 has no SI/self-harm content anywhere in its persona
file; this pack preserves that: `suicidal_ideation`/self-harm stay "없음" every session).
Setback trigger is grounded in the persona's OWN documented root stressor pattern (담임 +
생활지도부 업무 과부하, `VP-002_revisit_mild.md:112`) recurring via a new semester assignment —
never an invented, unrelated stressor.
"""

from __future__ import annotations

from tests.simulation.scenario_pack import ScenarioSession

# 10-session day-offset schedule (brainstorm design choice for this mission's 5-VP batch,
# distinct from EXP-023's 11-session schedule per the user's explicit "10 sessions" directive):
# 4 weekly (acute engagement) -> 3 biweekly (response consolidation) -> 3 tapered-monthly
# (maintenance), day 0 -> day 183 (~6.0 months, satisfies "<=6 months").
DAY_OFFSETS: list[int] = [0, 7, 14, 21, 35, 49, 63, 91, 137, 183]


def _phase_for(session_index: int) -> str:
    if session_index <= 4:
        return "acute_engagement"
    if session_index <= 7:
        return "response_consolidation"
    return "maintenance"


_STATES: list[str] = [
    # S1 — day0, = persona's own documented "current (재진)" state, verbatim-grounded
    "6주 전 경도 우울로 첫 방문 후 재진. Escitalopram 10mg 복용 6주째로 전반적으로 호전 "
    "경향입니다. 수면은 6-7시간으로 회복됐고 잠들기까지 30분 이내, 식욕도 정상 범위로 "
    "돌아왔습니다. 가끔 우울감이 들지만 빈도는 줄었고, 업무 스트레스가 남아 있어 완전한 "
    "회복에는 이르지 못한 상태입니다.",
    # S2
    "지난 상담 이후에도 꾸준히 호전되고 있습니다. 수면이 안정적으로 6-7시간 유지되고, "
    "약 복용도 거의 매일 잘 지키고 있습니다.",
    # S3
    "컨디션이 계속 좋습니다. 2주 만에 처음으로 짧은 산행을 다녀왔고, 예전 취미에 대한 "
    "흥미가 조금씩 돌아오는 느낌입니다.",
    # S4
    "거의 정상 범위에 가깝게 느껴집니다. 수업 준비도 무리 없이 하고 있고, 특별한 우울감 "
    "없이 지낸 날이 대부분입니다.",
    # S5 — consolidation begins, stable
    "안정적인 상태가 이어지고 있습니다. 동료 교사들과의 소모임에도 한 번 참석했습니다.",
    # S6 — setback trigger: new semester assignment recurs the original stressor
    "새 학기가 시작되면서 다시 담임과 생활지도부 업무를 함께 맡게 됐습니다. 예전 기억이 "
    "떠올라 약간 긴장되고, 수면이 살짝 흐트러지기 시작했습니다.",
    # S7 — setback peak
    "새 학기 업무가 몰리면서 며칠간 약 복용을 두 번 빠뜨렸습니다. 의욕 저하와 피로감이 "
    "다시 심해졌고, 수면도 5시간 정도로 줄었습니다. 스트레스 해소로 술을 주 2회 정도로 "
    "다시 늘렸습니다.",
    # S8 — maintenance begins, recovery resumes
    "아내가 약 복용을 다시 챙겨주기 시작하면서 순응도가 회복됐습니다. 수면도 다시 나아지고 "
    "있고, 업무도 조금씩 적응해가는 중입니다.",
    # S9
    "안정을 되찾았습니다. 수면 6-7시간, 특별한 우울감 없이 한 달을 보냈습니다.",
    # S10 — final, better than baseline
    "6주 전 재진 때와 비교해도 전반적으로 더 안정적입니다. 새 학기 업무도 이제는 감당할 "
    "만하다고 느끼고, 약물 감량에 대해 다음에 상의해보고 싶다는 생각이 듭니다.",
]

_EVENTS: list[list[str]] = [
    [],
    ["약 복용을 거의 매일 지킴", "특별한 사건 없이 안정적인 한 주"],
    ["2주 만에 짧은 산행을 다녀옴"],
    ["수업 준비를 무리 없이 소화함"],
    ["동료 교사 소모임에 한 번 참석함"],
    ["새 학기 시작 — 담임 + 생활지도부 업무를 다시 맡게 됨"],
    ["새 학기 업무 과부하로 약 복용을 2회 빠뜨림", "스트레스 해소용 음주가 주 2회로 늘어남"],
    ["아내가 약 복용을 다시 챙겨주기 시작함"],
    ["특별한 사건 없이 안정적인 한 달"],
    ["새 학기 업무에 적응하며 별다른 위기 없이 지나감"],
]

_REVEALS: list[str] = [
    "이전 상담(6주 전)과 비교해 좋아진 부분(수면, 식욕, 기분)을 밝은 톤으로 이야기하되, "
    "아직 업무 스트레스는 남아 있다는 뉘앙스를 유지하세요.",
    "꾸준한 호전을 담담하게 보고하세요. 약 복용 순응도가 좋다는 점을 자연스럽게 언급하세요.",
    "취미(산행)를 다시 시작한 것에 대해 스스로 뿌듯해하는 톤으로 이야기하세요.",
    "거의 정상 범위에 가까워졌다는 자신감을 담아 말하되, 과장하지는 마세요.",
    "안정적인 상태를 짧고 긍정적으로 요약하세요.",
    "새 학기 업무 재개로 인한 긴장을 조심스럽게 인정하세요. 예전 경험이 떠오른다는 점을 "
    "자연스럽게 언급하되, 아직 심각한 수준은 아니라는 뉘앙스를 유지하세요.",
    "복약 순응도 저하와 증상 재발을 솔직하게, 다소 자책하는 톤으로 인정하세요. 완전히 예전 "
    "수준으로 돌아간 것은 아니라는 점도 함께 말하세요.",
    "아내의 도움으로 다시 궤도에 오르고 있다는 점을 감사하는 톤으로 이야기하세요.",
    "안정된 한 달을 담백하게 요약하세요.",
    "6주 전과 비교한 전반적 호전을 스스로 되짚어보는 톤으로, 약물 감량 논의에 대한 관심도 "
    "자연스럽게 언급하세요.",
]

_PHQ9_TARGETS = [
    "~7", "~6", "~5", "~4", "~4", "~6 (setback onset)", "~10 (setback peak)", "~6", "~5", "~4",
]
_GAD7_TARGETS = ["~5", "~5", "~4", "~3", "~3", "~5", "~8 (setback peak)", "~5", "~4", "~3"]
_CTRS_TARGETS = ["5", "5", "5", "5", "5", "4", "4", "5", "5", "5"]

assert len({
    len(_STATES), len(_EVENTS), len(_REVEALS),
    len(_PHQ9_TARGETS), len(_GAD7_TARGETS), len(_CTRS_TARGETS), len(DAY_OFFSETS),
}) == 1

VP_002_TREATMENT_RESPONSE_SETBACK: tuple[ScenarioSession, ...] = tuple(
    ScenarioSession(
        session_index=i + 1,
        day_offset=DAY_OFFSETS[i],
        arc_mode="treatment_response_setback",
        phase_label=_phase_for(i + 1),
        state_descriptor_ko=_STATES[i],
        inter_session_events_ko=list(_EVENTS[i]),
        symptom_targets={
            "PHQ-9": _PHQ9_TARGETS[i], "GAD-7": _GAD7_TARGETS[i], "CTRS": _CTRS_TARGETS[i],
        },
        reveal_guidance_ko=_REVEALS[i],
    )
    for i in range(10)
)

# NOTE for the developer wiring this in: `ScenarioSession.scenario_pack_id` resolves via
# `scenario_pack.py`'s private `_ARC_MODE_TO_PERSONA` dict, which does not yet know
# "treatment_response_setback" -> "VP-002" (only the 2 EXP-023 arc_modes are registered there
# today) — add that mapping entry when wiring this pack in, or the property raises KeyError.
# Uniqueness is checked here directly against the intended id shape instead, to avoid depending
# on that not-yet-updated mapping.
_ids = [
    f"VP-002_treatment_response_setback_s{s.session_index:02d}"
    for s in VP_002_TREATMENT_RESPONSE_SETBACK
]
assert len(set(_ids)) == len(_ids), f"scenario_pack_id collision: {_ids}"
