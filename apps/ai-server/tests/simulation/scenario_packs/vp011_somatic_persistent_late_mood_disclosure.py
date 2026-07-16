"""VP-011 longitudinal arc pack — `somatic_persistent_late_mood_disclosure` — brainstorm design
deliverable.

**DEVIATION FROM PERSONA FILE — recorded here, persona file itself NOT edited (per coordinator
ruling, 2026-07-15):** `docs/ai/personas/VP-011_first_visit_somatic.md`'s header and §8 state "No
multi-session run is scheduled for this persona (SC-12 dialogue-only)" and treat the
reveal-partition gate as EXEMPT on that basis. That statement was a W6 design-time SCOPING note
(SC-12's battery was dialogue-only-first-visit by construction, not a clinical constraint on the
persona itself) — the user's current directive ("모든 VP에 대해 최대 6개월, 최대 10개 세션 시나리오
아크로 F1-F5 total-validation cohort 완성") supersedes that scoping for this mission. This arc pack
therefore DOES schedule a multi-session run for VP-011, and — because a real reveal-partition gate
now exists for the first time (see below) — this file authors that gate explicitly, closing the
exemption rather than leaving it dangling. **This arc is flagged for clinical-validator (CVR)
review together with the other 4 new arcs** before any harness wiring, per the coordinator's
explicit instruction; no ADR ratifying this deviation exists yet — that is the clinical-validator
/ critic gate's job, not brainstorm's.

Schema/location convention mirrors `tests/simulation/scenario_pack.py` (EXP-023 precedent). Not
yet wired into `_SCENARIO_PACKS`. See `vp002_treatment_response_setback.py`'s docstring for the
shared `scenario_pack_id` wiring caveat.

## Reveal-partition table (this arc's own gate design — required per coordinator instruction (b))

Grounded in `docs/ai/personas/VP-011_first_visit_somatic.md` (read in full). The persona's own §2
"기저 진단" anchor (중등도 MDD) and §5 masking pattern are preserved verbatim as this arc's ground
truth; what this arc ADDS is a session-indexed gate on WHEN the mood component becomes reachable,
per the user's "somatic-presentation persists, mood disclosure emerges late (session 7+)" directive:

| Persona fact | Gate | Sessions reachable |
|---|---|---|
| Surface somatic complaints (두통/소화불량/피로) | never gated | S1-S10, every session, freely and in detail |
| Anhedonia probe-reveal (등산 중단, "귀찮다") — needs the persona's own specific interest-probe | never gated (probe-dependent, not session-dependent — same as original single-session design) | S1-S10, IF the specific probe is asked that session |
| Pain-independent sleep-disruption probe-reveal — needs the persona's own specific pain-independence probe | never gated (probe-dependent) | S1-S10, IF the specific probe is asked that session |
| Direct "우울증"/기분 문제 명명에 대한 부인 ("아닌 것 같은데요") | default response | S1-S6 (dominant); S7+ softens (see below) — never a hard denial after S7 |
| **Spontaneous, unprompted mood-connection acknowledgment** ("기분도 좀... 그런 것 같기도") | **GATED — new gate this arc introduces** | **NOT reachable before S7, regardless of probing quality; first appears S7** |
| Agreement to a psychiatry referral / co-managed care | GATED | S8+ |
| Behavioral activation attempt (한 차례 등산 재개) | GATED | S9+ |
| Partial integration — mood named as a contributing factor (not a full "depression" self-label) | GATED | S10 (arc close) |

This gate exists so that a harness run cannot show mood-connection content before S7 even under
skilled probing (S1-S6 probes still reveal anhedonia/sleep-independence as isolated facts, per the
persona's original single-session design — but never the *connective* insight that these relate to
mood, which is the new, session-gated content). `data`/`clinical-validator` should treat the S1-S6
probe-reveals as testing the SAME probing-skill dimension the original persona already tested
(§8's two named probe->reveal pairs), and the S7+ spontaneous content as testing a NEW
longitudinal dimension (does the system's F4 change-detection notice a late-emerging domain shift
from somatic-only to somatic+mood) — the two should not be conflated in scoring.
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
    # S1 — day0, = persona's own documented first-visit state (somatic-focal, mood only via probe)
    "2개월 이상 지속된 만성 두통·소화불량·만성피로로 첫 방문. 내과 2곳 방문, 위내시경/혈액검사 "
    "모두 정상이었습니다. 본인은 신체 질환으로 귀인하며, 기분 문제는 명시적으로 언급하지 "
    "않습니다(ground truth: 중등도 주요우울장애, 기저 진단 anchor).",
    # S2
    "두통이 계속되어 새로운 진통제를 시도해봤지만 큰 차도가 없습니다. 등산 등 이전 취미는 "
    "여전히 가지 않고 있습니다.",
    # S3
    "신경과 진료를 받았으나 정상 소견이었습니다. \"검사마다 정상이래요\"라며 답답함을 "
    "표현합니다.",
    # S4
    "소화기내과 재진도 정상이었습니다. 피로감은 오히려 더 심해진 느낌입니다. 여전히 신체 "
    "문제로 귀인하고 있습니다.",
    # S5 — consolidation begins
    "수면이 더 나빠졌습니다. 통증이 없는 날에도 여전히 새벽에 깹니다. 담당의가 스트레스와의 "
    "연관 가능성을 처음 언급했으나, 본인은 여전히 방어적입니다.",
    # S6 — skepticism begins to soften slightly (still no spontaneous mood link)
    "스트레스 이야기에 대해 예전만큼 방어적이지는 않게 됐습니다. 다만 이것을 기분 문제로 "
    "연결짓지는 않습니다. 에너지·흥미 저하는 그대로 지속됩니다.",
    # S7 — GATED: mood-connection first spontaneously emerges (response_consolidation ends)
    "이번 세션에서 처음으로, 캐묻지 않았는데도 \"사실 요즘 기분도 좀... 그런 것 같기도 "
    "하고요\"라며 스스로 기분과의 연관성을 조심스럽게 언급했습니다. 여전히 신체 증상이 "
    "주된 프레임이지만, 처음으로 균열이 생겼습니다.",
    # S8 — maintenance begins, GATED: referral agreement
    "정신건강의학과 공동 관리(co-managed care) 제안에 동의했습니다. 여전히 조심스럽지만, "
    "\"한번 같이 봐도 나쁘지 않을 것 같다\"고 말했습니다. 두통 빈도가 스트레스 인식과 함께 "
    "약간 줄었습니다.",
    # S9 — GATED: behavioral activation attempt
    "3개월 만에 처음으로 짧은 등산을 한 번 다녀왔습니다. 신체 증상은 여전하지만 강도는 "
    "다소 낮아졌습니다. \"우울증까지는 모르겠지만\"이라는 표현을 쓰며 기분 요인을 좀 더 "
    "직접적으로 언급하기 시작했습니다.",
    # S10 — final, GATED: partial integration
    "6개월 전과 비교하면 신체 증상은 여전히 남아 있지만 강도는 낮아졌고, 기분 요인이 "
    "여기에 기여하고 있다는 것을 이제는 스스로 인정합니다. \"완전히 우울증이라고는 생각 "
    "안 하지만, 마음도 어느 정도 관련 있는 것 같아요\"라는 부분적 통합을 보입니다.",
]

_EVENTS: list[list[str]] = [
    [],
    ["새로운 진통제를 시도했으나 큰 차도 없음"],
    ["신경과 진료 — 정상 소견"],
    ["소화기내과 재진 — 정상 소견"],
    ["담당의가 스트레스-신체증상 연관 가능성을 처음 언급함"],
    ["특별한 외부 사건 없음 — 스트레스 논의에 대한 방어 태도가 소폭 완화됨"],
    ["특별한 외부 사건 없음 — 상담 내에서 첫 자발적 기분-연관 언급 발생"],
    ["정신건강의학과 공동 관리 제안에 동의함"],
    ["3개월 만에 짧은 등산을 한 번 다녀옴"],
    ["큰 사건 없이 안정적으로 지나감"],
]

_REVEALS: list[str] = [
    "주호소는 항상 신체 증상으로 먼저 상세하게 말하세요. 기분을 직접 물으면 즉시 신체로 "
    "재귀인하세요. 흥미/수면-무관성에 대한 구체적 probe를 받을 때만 해당 사실을 인정하세요 "
    "(우울증이라는 명명 자체는 여전히 거부).",
    "여전히 신체 증상 중심으로 상세히 답하세요. 흥미 probe를 받으면 등산 중단 사실을 "
    "인정하되, 기분과 연결짓지는 마세요.",
    "검사 결과가 계속 정상이라는 것에 대한 답답함을 표현하세요. 여전히 신체 프레임을 "
    "유지하세요.",
    "피로감 심화를 신체적으로 설명하세요. 정서 관련 질문에는 여전히 짧고 방어적으로 "
    "답하세요.",
    "스트레스 연관 가능성에 대해 처음으로 완전히 부인하지는 않되, 여전히 조심스럽고 "
    "방어적인 톤을 유지하세요. 통증-무관 수면 probe를 받으면 사실을 인정하세요.",
    "스트레스 이야기에 예전보다 덜 방어적으로 반응하세요. 그러나 스스로 먼저 기분과 "
    "연결짓지는 마세요 — 이 전환은 다음 세션(S7)에만 일어납니다.",
    "이번 세션에서는 캐묻지 않아도 스스로 기분과의 연관성을 조심스럽게, 처음으로 "
    "언급하세요(\"사실 요즘 기분도 좀... 그런 것 같기도 하고요\"). 여전히 신체 증상이 "
    "주된 설명 틀임을 유지하되, 완전한 부인에서는 벗어나세요.",
    "공동 관리 제안에 조심스럽게 동의하는 톤으로 답하세요. 신체 증상 완화를 스트레스 "
    "인식과 연결지어 담담하게 언급하세요.",
    "등산 재개를 스스로도 약간 놀라워하는 톤으로 이야기하세요. \"우울증까지는 모르겠지만\" "
    "같은 헤지 표현과 함께 기분 요인을 조금 더 직접적으로 언급하세요.",
    "부분적 통합을 표현하세요 — 완전한 \"우울증\" 자기 명명은 여전히 피하되, 마음의 "
    "요인이 어느 정도 관련되어 있음을 스스로 인정하는 톤으로 마무리하세요. 자살/자해 "
    "질문에는 항상 분명하게 \"전혀 없다\"고 답하세요.",
]

_PHQ9_TARGETS = ["~14", "~14", "~14", "~15", "~14", "~13", "~13", "~12", "~11", "~10"]
_GAD7_TARGETS = ["~7", "~7", "~7", "~8", "~7", "~7", "~6", "~6", "~5", "~5"]
_CTRS_TARGETS = ["4", "4", "4", "4", "4", "4", "4", "4", "4", "4"]
_MOOD_GATE_STATUS = [
    "somatic-only (probe-reachable: anhedonia, sleep-independence)",
    "somatic-only", "somatic-only", "somatic-only",
    "somatic-only, defensiveness softening",
    "somatic-only, no spontaneous mood link yet",
    "GATE OPENS — first spontaneous mood-connection",
    "referral agreement (gated)",
    "behavioral activation attempt (gated)",
    "partial integration (gated, arc close)",
]

assert len({
    len(_STATES), len(_EVENTS), len(_REVEALS), len(_PHQ9_TARGETS),
    len(_GAD7_TARGETS), len(_CTRS_TARGETS), len(_MOOD_GATE_STATUS), len(DAY_OFFSETS),
}) == 1

VP_011_SOMATIC_PERSISTENT_LATE_MOOD_DISCLOSURE: tuple[ScenarioSession, ...] = tuple(
    ScenarioSession(
        session_index=i + 1,
        day_offset=DAY_OFFSETS[i],
        arc_mode="somatic_persistent_late_mood_disclosure",
        phase_label=_phase_for(i + 1),
        state_descriptor_ko=_STATES[i],
        inter_session_events_ko=list(_EVENTS[i]),
        symptom_targets={
            "PHQ-9": _PHQ9_TARGETS[i],
            "GAD-7": _GAD7_TARGETS[i],
            "CTRS": _CTRS_TARGETS[i],
            "mood_gate_status": _MOOD_GATE_STATUS[i],
        },
        reveal_guidance_ko=_REVEALS[i],
    )
    for i in range(10)
)

# See vp002_treatment_response_setback.py docstring: `_ARC_MODE_TO_PERSONA` needs a
# "somatic_persistent_late_mood_disclosure" -> "VP-011" entry added at wiring time.
_ids = [
    f"VP-011_somatic_persistent_late_mood_disclosure_s{s.session_index:02d}"
    for s in VP_011_SOMATIC_PERSISTENT_LATE_MOOD_DISCLOSURE
]
assert len(set(_ids)) == len(_ids), f"scenario_pack_id collision: {_ids}"
