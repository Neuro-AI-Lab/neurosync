"""VP-012 longitudinal arc pack — `aud_escalation_contemplation` — brainstorm design deliverable.

Schema/location convention mirrors `tests/simulation/scenario_pack.py` (EXP-023 precedent). Not
yet wired into `_SCENARIO_PACKS` — pending critic REV + clinical-validator CVR (flagged for review
together with the other 4 new arcs, per coordinator instruction, 2026-07-15). See
`vp002_treatment_response_setback.py`'s docstring for the shared `scenario_pack_id` wiring caveat.

Grounded in `docs/ai/personas/VP-012_first_visit_alcohol.md` (read in full, including its §9
AUDIT-C v2 soju-track re-derivation) — S1 of this arc reuses the persona's own documented
first-visit ground truth verbatim (§2/§3/§4: AUDIT-C 8 (range 7-9, soju-track v2), PHQ-9 ~10,
alcohol as the explicit stated presenting concern, SI unconditionally negative throughout). No
crisis content is added anywhere in this arc — the persona's own §8 "no crisis-content licensing"
note holds unchanged at every session.

Arc shape (per user directive): AUD trajectory — escalation, then a shift into the contemplation
stage (Prochaska & DiClemente's transtheoretical stages-of-change model: precontemplation ->
contemplation -> preparation/action; movement between stages is non-linear and typically cyclical,
not a single clean transition — this arc scripts one escalation-then-turning-point cycle, not a
completed recovery, per the model as generally described). Depression comorbidity (§2's
"동반 상태" note) is carried forward and tracked in parallel, staying mild-to-moderate throughout,
never becoming the primary focus (matching the persona's own binding "알코올이 임상적 초점" design).
Basis: transtheoretical/stages-of-change model description is general clinical-literature
background (search-result summaries), not a specific-paper claim — see files below for sources;
*summary basis: search-result summaries, not full-text/primary-source reads*.
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
    # S1 — day0, = persona's own documented first-visit state
    "최근 건강검진에서 간 수치(AST/ALT/GGT) 이상이 발견되어 첫 방문. 8-10년간 거의 매일 "
    "소주 1병 이상 음주(위험 음주 수준), 절주 시도 여러 번 실패, 조절 상실감·"
    "갈망 있음. 경미-중등도 우울 증상 동반이나 본인은 이를 음주 문제의 결과로 "
    "인식. 자살/자해 사고 없음(명확, 일관).",
    # S2 — early ambivalent attempt, fails (precontemplation/early contemplation ambivalence)
    "건강검진 결과에 놀라 이틀 정도 술을 줄여봤지만 곧 다시 이전 수준으로 돌아왔습니다. "
    "\"의지로 안 되더라고요\"라는 말을 반복합니다.",
    # S3
    "재검사 결과를 기다리는 중입니다. 식당 운영 스트레스가 겹치면서 음주량이 다시 소폭 "
    "늘었습니다.",
    # S4
    "배우자와 음주 문제로 다툼이 있었습니다. 죄책감을 느끼지만 음주 패턴에는 큰 변화가 "
    "없습니다.",
    # S5 — consolidation begins, escalation peak
    "식당 비수기로 경제적 스트레스가 커지면서, \"한 병 반\"을 마시는 날이 더 잦아졌습니다. "
    "수면이 더 얕아졌고, 기분도 예전보다 약간 더 가라앉아 있습니다(경도-중등도 우울 소폭 "
    "악화).",
    # S6 — external prompt: follow-up labs
    "재검사에서 간 수치가 여전히 높거나 소폭 더 나빠진 것으로 나왔습니다. 이 결과를 보고 "
    "\"이건 진짜 문제구나\" 싶은 생각이 처음으로 명확하게 들었다고 말합니다.",
    # S7 — shift into contemplation (response_consolidation ends)
    "배우자가 진지하게 대화를 요청했고, 본인이 상담을 받아보라고 이야기했습니다. 처음으로 "
    "\"정말 줄여야 하나 싶어요\"라며 변화에 대한 양가감정을 openly 드러냈습니다. 아직 "
    "음주량 자체는 크게 줄지 않았습니다.",
    # S8 — maintenance begins, first sustained cut-down attempt
    "처음으로 지속적인 절주 시도를 시작했습니다 — 거의 매일에서 주 5회 정도로 줄였습니다. "
    "여전히 완전히 끊지는 못했고, 안 마시는 날에는 갈망을 느낀다고 말합니다.",
    # S9 — continued partial reduction
    "음주 빈도가 주 4회 정도로 더 줄었고, 폭음(1.5병) 빈도도 줄었습니다. 기분도 조금 "
    "나아졌고, 배우자가 노력을 알아봐 주는 것 같아 다행이라고 말합니다.",
    # S10 — final, stabilized in contemplation-to-early-action, not full remission
    "6개월 전과 비교하면 음주량이 의미 있게 줄었지만(거의 매일 1병+ -> 주 4회, 폭음 빈도 "
    "감소), 완전히 끊은 것은 아닙니다. 재검사를 다시 받을 예정이며, 동반된 우울 증상도 "
    "소폭 나아졌습니다(경도 완화). \"많이 줄이긴 했는데, 완전히 끊을 수 있을진 "
    "모르겠어요\"라며 현실적인 태도를 보입니다.",
]

_EVENTS: list[list[str]] = [
    [],
    ["건강검진 결과 이후 이틀간 절주 시도 — 곧 이전 수준으로 복귀"],
    ["간 기능 재검사 대기 중", "식당 운영 스트레스 증가"],
    ["배우자와 음주 문제로 다툼"],
    ["식당 비수기로 경제적 스트레스 증가", "폭음(1.5병) 빈도 증가"],
    ["간 기능 재검사 결과 — 여전히 이상 소견 (소폭 악화)"],
    ["배우자와 진지한 대화 — 상담 지속을 권유받음"],
    ["첫 지속적 절주 시도 시작 (거의 매일 -> 주 5회)"],
    ["음주 빈도 추가 감소 (주 4회), 폭음 빈도 감소"],
    ["재검사 예정 안내, 큰 위기 없이 지나감"],
]

_REVEALS: list[str] = [
    "음주에 대해서는 방어적이지 않고 사실 그대로 답하세요(양, 빈도, 조절 상실감, 갈망, "
    "절주 시도 실패 이력). 자살/자해 질문에는 항상 분명하게 \"전혀 없다\"고 답하세요.",
    "짧은 절주 시도와 그 실패를 담담하게, 약간의 자책과 함께 이야기하세요.",
    "재검사 대기 중의 불안과 스트레스로 인한 음주 증가를 사실적으로 말하세요.",
    "배우자와의 다툼과 죄책감을 담담한 어조로 인정하세요. 과장하지 마세요.",
    "경제적 스트레스로 인한 음주 증가를 구체적으로 이야기하세요. 기분 저하도 짧게 "
    "언급하되 음주 문제와 결부지어 설명하세요.",
    "재검사 결과에 대한 걱정을 처음으로 명확하게 표현하세요 — \"이건 진짜 문제구나\" 같은 "
    "인식 전환을 담담하지만 진지한 톤으로 드러내세요.",
    "변화에 대한 양가감정을 openly 드러내세요 — 아직 확신은 없지만 진지하게 고민하고 "
    "있다는 톤을 유지하세요.",
    "처음 시도하는 지속적 절주를 조심스러운 자부심과 함께 이야기하되, 갈망이 여전히 "
    "있다는 것도 솔직하게 인정하세요.",
    "점진적 호전을 담담하게, 배우자의 반응에 대한 안도감과 함께 이야기하세요.",
    "의미 있지만 불완전한 변화를 현실적으로 표현하세요 — 완전한 회복이나 금주 선언이 "
    "아니라, 실질적으로 줄었다는 사실과 앞으로의 불확실성을 함께 인정하세요. 자살/자해 "
    "질문에는 항상 분명하게 \"전혀 없다\"고 답하세요.",
]

_AUDITC_TARGETS = [
    "8 (range 7-9, baseline)", "8 (attempt failed, reverted)", "8-9 (stress uptick)",
    "8-9", "9-10 (escalation peak)", "9 (post-labs, unchanged drinking yet)",
    "8-9 (ambivalence, drinking not yet reduced)", "6-7 (first sustained reduction, ~5x/week)",
    "5-6 (~4x/week, binge frequency down)", "5-6 (stabilized, partial reduction, not abstinent)",
]
_PHQ9_TARGETS = [
    "~10", "~10", "~10", "~11", "~12 (mild worsening)", "~11", "~11", "~10", "~9", "~8",
]
_CTRS_TARGETS = ["4", "4", "4", "4", "4", "4", "4", "4", "4", "4"]
_STAGE_OF_CHANGE = [
    "precontemplation", "precontemplation (ambivalent attempt, failed)", "precontemplation",
    "precontemplation", "precontemplation (escalation peak)",
    "precontemplation->contemplation transition",
    "contemplation (openly ambivalent)", "contemplation->early action (first sustained attempt)",
    "action (partial)", "action (partial, stabilizing)",
]

assert len({
    len(_STATES), len(_EVENTS), len(_REVEALS), len(_AUDITC_TARGETS),
    len(_PHQ9_TARGETS), len(_CTRS_TARGETS), len(_STAGE_OF_CHANGE), len(DAY_OFFSETS),
}) == 1

VP_012_AUD_ESCALATION_CONTEMPLATION: tuple[ScenarioSession, ...] = tuple(
    ScenarioSession(
        session_index=i + 1,
        day_offset=DAY_OFFSETS[i],
        arc_mode="aud_escalation_contemplation",
        phase_label=_phase_for(i + 1),
        state_descriptor_ko=_STATES[i],
        inter_session_events_ko=list(_EVENTS[i]),
        symptom_targets={
            "AUDIT-C": _AUDITC_TARGETS[i],
            "PHQ-9": _PHQ9_TARGETS[i],
            "CTRS": _CTRS_TARGETS[i],
            "stage_of_change": _STAGE_OF_CHANGE[i],
        },
        reveal_guidance_ko=_REVEALS[i],
    )
    for i in range(10)
)

# See vp002_treatment_response_setback.py docstring: `_ARC_MODE_TO_PERSONA` needs an
# "aud_escalation_contemplation" -> "VP-012" entry added at wiring time.
_ids = [
    f"VP-012_aud_escalation_contemplation_s{s.session_index:02d}"
    for s in VP_012_AUD_ESCALATION_CONTEMPLATION
]
assert len(set(_ids)) == len(_ids), f"scenario_pack_id collision: {_ids}"
