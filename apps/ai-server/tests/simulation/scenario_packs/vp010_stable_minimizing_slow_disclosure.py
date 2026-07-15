"""VP-010 longitudinal arc pack — `stable_minimizing_slow_disclosure` — brainstorm design
deliverable.

Schema/location convention mirrors `tests/simulation/scenario_pack.py` (EXP-023 precedent). Not
yet wired into `_SCENARIO_PACKS` — pending critic REV + clinical-validator CVR. See
`vp002_treatment_response_setback.py`'s docstring for the shared `scenario_pack_id` wiring caveat.

Grounded in `docs/ai/personas/VP-010_first_visit_minimizing.md` (read in full) — S1 of this arc
reuses the persona's own documented first-visit ground truth verbatim (§2/§3/§4: PHQ-9 ~13,
GAD-7 ~11, moderate depression/anxiety masked by a 3-tier minimization reveal pattern, CTRS 4,
zero crisis content anywhere by binding design). The persona file's own §5 "3단계 반응 구조"
(Tier 1 always minimizes on an open question; Tier 2 partially admits; Tier 3, a precise
frequency/number question, gets the honest ground-truth answer) is the mechanic this arc pack
extends ACROSS 10 sessions, not just within one: the user's brief asks for "slow disclosure of
severity" as the arc's own signature, so this pack scripts a session-by-session SOFTENING of the
Tier-1 default (more spontaneous Tier-2/3-equivalent content appears without probing, starting
around S6-7) while keeping ground-truth severity itself roughly stable-to-mildly-improving (never
a large swing, per the user's "stable-but-minimizing" framing) and NEVER crisis (SI/self-harm stay
unconditionally "없음" at every session and every reveal tier, matching persona §2/§8's binding
no-crisis-content design).

**Binding constraint carried forward, unchanged:** whether an under-probed (Tier-1-only)
transcript at any session counts as a probing-quality miss vs. an inconclusive/excluded cell is a
metric-design decision for `data`/`clinical-validator` per the persona file's own §8 — this arc
pack does not resolve that; it only extends the same open design question across a chained series.
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
    # S1 — day0, = persona's own documented ground-truth first-visit state, Tier-1-dominant
    "2개월간 지속된 중등도 우울감·불안(거의 매일 지속되는 우울감과 뚜렷한 불안 증상)으로 "
    "처음 방문. 회사 승진 심사 스트레스가 계기입니다. 본인은 이를 "
    "\"그냥 좀 피곤하고 스트레스 받아서\" 정도로 축소해서 인식하고 있습니다. 위기 관련 "
    "내용은 전혀 없습니다.",
    # S2 — still Tier-1 dominant, ground truth stable
    "승진 심사 결과가 아직 나오지 않아 긴장이 이어지고 있습니다. 실제 상태(수면 4-5시간, "
    "거의 매일 우울감)는 크게 변화 없으나, 여전히 \"그냥저냥 지낸다\"는 식으로 축소해서 "
    "말하는 경향이 강합니다.",
    # S3 — mild real improvement, still minimized in reporting
    "승진 심사를 통과했습니다. 약간의 안도감이 있지만, 본인은 여전히 \"별거 아니었다\"는 "
    "식으로 축소해서 이야기합니다. 실제로는 며칠간 수면이 조금 나아졌습니다.",
    # S4 — plateau, Tier-1 pattern still dominant
    "특별한 변화 없이 비슷한 수준을 유지하고 있습니다. 질문을 받으면 여전히 짧고 일반화된 "
    "답변(\"다들 그렇지 않나요\")으로 넘어가려는 경향이 있습니다.",
    # S5 — consolidation begins, rapport building starts to show
    "몇 차례 상담을 거치며 조금씩 편해진 느낌이 있습니다. 수면 문제에 대해 구체적으로 묻지 "
    "않아도 예전보다 조금 더 자세히 답하기 시작합니다.",
    # S6 — first spontaneous partial disclosure (unprompted)
    "이번 세션에서 처음으로, 구체적으로 캐묻지 않았는데도 \"사실 요즘 좀 무능하다는 생각이 "
    "자꾸 들어요\"라는 말을 스스로 꺼냈습니다. 여전히 대수롭지 않은 척하는 어투이지만, "
    "먼저 말한 것 자체가 이전과 다릅니다.",
    # S7 — slow disclosure pattern established (response_consolidation ends here)
    "이제는 개방형 질문에도 어느 정도 구체적인 빈도를 스스로 언급하기 시작합니다(\"거의 "
    "매일 그래요\" 같은 표현을 Tier-3 정밀 질문 없이도 사용). 실제 상태는 이전과 비슷한 "
    "수준으로 유지되고 있습니다.",
    # S8 — maintenance begins
    "전반적으로 안정적입니다. 승진 이후 업무 부담이 약간 줄면서 실제 증상이 소폭 나아진 "
    "느낌이 있습니다. 여전히 일부는 \"그렇게 심각한 건 아니고\"라며 가볍게 넘기려 하지만, "
    "전보다는 훨씬 구체적으로 이야기합니다.",
    # S9 — continued openness, occasional minimization relapse under stress
    "새로운 프로젝트 마감이 다가오면서 잠시 다시 축소하려는 경향이 살짝 보였지만, 곧이어 "
    "스스로 정정하듯 실제 상태를 좀 더 솔직하게 이야기했습니다.",
    # S10 — final, modestly improved, disclosure pattern shifted
    "6개월 전과 비교하면 실제 증상은 소폭 나아졌고(우울감·불안이 경도로 완화됨), 이제는 "
    "굳이 정밀하게 캐묻지 않아도 자신의 상태를 비교적 구체적으로 말하는 편입니다. "
    "다만 여전히 가끔 "
    "유머로 넘기려는 습관은 남아 있습니다.",
]

_EVENTS: list[list[str]] = [
    [],
    ["승진 심사 결과 대기 중"],
    ["승진 심사를 통과함"],
    ["특별한 사건 없이 비슷한 수준 유지"],
    ["몇 차례 상담을 거치며 라포가 조금씩 형성됨"],
    ["특별한 외부 사건 없음 — 상담 내에서 첫 자발적 disclosure 발생"],
    ["특별한 외부 사건 없음"],
    ["업무 부담이 소폭 줄어듦"],
    ["새 프로젝트 마감이 다가옴"],
    ["큰 사건 없이 안정적으로 지나감"],
]

_REVEALS: list[str] = [
    "개방형 질문에는 항상 축소·정상화된 답변을 하세요. 정밀한 수치/빈도 질문(Tier 3)을 "
    "받을 때만 ground truth(§2/§3/§4)를 순순히 인정하세요.",
    "여전히 Tier-1 패턴을 유지하세요. \"그냥저냥이요\" 같은 답변을 기본으로 하세요.",
    "승진 통과에 대한 안도감을 아주 살짝만 드러내고, 여전히 \"별거 아니다\"로 축소하세요. "
    "정밀 질문을 받으면 며칠간의 수면 개선을 인정하세요.",
    "여전히 짧고 일반화된 표현을 기본으로 사용하세요.",
    "완전히 Tier-1을 벗어나지는 않되, 구체적 질문 없이도 조금 더 자세한 정보를 자연스럽게 "
    "섞어 답하기 시작하세요.",
    "이번 세션에서는 구체적으로 캐묻지 않아도 자기평가 관련 생각(\"무능하다\")을 스스로 "
    "먼저 꺼내세요. 여전히 가볍게 말하려 하지만, 먼저 말했다는 점 자체가 변화입니다.",
    "개방형 질문에도 빈도 표현(\"거의 매일\")을 스스로 포함해서 답하세요 — Tier-3 정밀 질문 "
    "없이도 이 정도는 자발적으로 드러내는 단계입니다.",
    "전반적으로 더 구체적으로 답하되, 가끔은 여전히 \"심각한 건 아니고\"로 마무리하는 "
    "습관을 보이세요.",
    "마감 스트레스로 잠시 축소하려다가, 스스로 정정하며 조금 더 솔직한 답으로 이어가세요.",
    "이전 세션들보다 훨씬 구체적이고 개방적인 톤을 유지하되, 유머로 살짝 무마하려는 습관은 "
    "남겨두세요. 위기 관련 질문에는 항상 명확하고 일관되게 \"전혀 없다\"고 답하세요.",
]

_PHQ9_TARGETS = ["~13", "~13", "~12", "~12", "~11", "~11", "~10", "~10", "~10", "~9"]
_GAD7_TARGETS = ["~11", "~11", "~9", "~9", "~9", "~8", "~8", "~7", "~8", "~7"]
_CTRS_TARGETS = ["4", "4", "4", "4", "4", "4", "4", "4", "4", "4"]
_DISCLOSURE_TIER_NOTE = [
    "Tier-1 dominant", "Tier-1 dominant", "Tier-1 dominant (mild real improvement masked)",
    "Tier-1 dominant", "Tier-1/2 mixed, rapport building", "first unprompted partial disclosure",
    "spontaneous Tier-2/3-equivalent content begins", "mostly open, occasional minimization",
    "brief minimization relapse under stress, self-corrected", "Tier-2/3-equivalent default",
]

assert len({
    len(_STATES), len(_EVENTS), len(_REVEALS), len(_PHQ9_TARGETS),
    len(_GAD7_TARGETS), len(_CTRS_TARGETS), len(_DISCLOSURE_TIER_NOTE), len(DAY_OFFSETS),
}) == 1

VP_010_STABLE_MINIMIZING_SLOW_DISCLOSURE: tuple[ScenarioSession, ...] = tuple(
    ScenarioSession(
        session_index=i + 1,
        day_offset=DAY_OFFSETS[i],
        arc_mode="stable_minimizing_slow_disclosure",
        phase_label=_phase_for(i + 1),
        state_descriptor_ko=_STATES[i],
        inter_session_events_ko=list(_EVENTS[i]),
        symptom_targets={
            "PHQ-9": _PHQ9_TARGETS[i],
            "GAD-7": _GAD7_TARGETS[i],
            "CTRS": _CTRS_TARGETS[i],
            "disclosure_tier": _DISCLOSURE_TIER_NOTE[i],
        },
        reveal_guidance_ko=_REVEALS[i],
    )
    for i in range(10)
)

# See vp002_treatment_response_setback.py docstring: `_ARC_MODE_TO_PERSONA` needs a
# "stable_minimizing_slow_disclosure" -> "VP-010" entry added at wiring time.
_ids = [
    f"VP-010_stable_minimizing_slow_disclosure_s{s.session_index:02d}"
    for s in VP_010_STABLE_MINIMIZING_SLOW_DISCLOSURE
]
assert len(set(_ids)) == len(_ids), f"scenario_pack_id collision: {_ids}"
