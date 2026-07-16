"""F4 quick-dev longitudinal scenario packs — harness/tests territory ONLY.

`docs/ai/f4_quick_dev_plan.md` §2.3/§2.4/§2.5, `PLAN-2026-W29-D`, `ADR-036`.
This module owns the 11-session arc CONTENT (state descriptors,
inter-session events, reveal guidance, day-offset schedule) for VP-001
(`improvement_plateau`) and VP-003 (`relapse_after_partial_improvement`) —
never `src/`. `src/f1.py` only gains two narrow, optional, `None`-default
kwargs (`scenario_guideline`/`scenario_pack_id`, design doc §2.6 option C);
the SCRIPT ITSELF lives entirely here.

`symptom_targets` is design-intent metadata for humans/report-reading only
— `render_scenario_guideline` NEVER renders it into the injected text (the
template below has no placeholder for it), matching the isolation
discipline design doc §2.5/§2.6 requires: the patient LLM is steered by
qualitative state/events/reveal-guidance only, never a number to "hit."

Content notes (ADR-036 dispositions, both binding on this file):
  - item 6 / CVR-020 Condition 2: VP-001's S1 `symptom_targets["PHQ-9"]` is
    the persona-documented mild baseline (~7, `VP-001_first_visit_mild.md`
    §3), NOT the previously-considered ~13 (a known EXP-019 over-triage
    artifact, CVR-015 Finding 2) — the whole VP-001 trajectory below is
    re-anchored to taper from that mild baseline, not from moderate.
    OBSERVED F3 totals may still ride the known whole-instrument
    over-endorsement offset (CVR-019 #1 / `ISS-F2V-028`) regardless of this
    design-intent target; any expected-vs-observed divergence is a
    reportable finding for the eventual EXP entry, never a reason to
    retroactively redefine `PLAN-2026-W29-D`'s acceptance criteria
    (REV-044 Criterion 1 discipline).
  - item 5 / CVR-020 binding condition 1: VP-003's S8 (first
    post-relapse-peak session) gains a NEW inter-session event depicting
    the patient acting on THIS SYSTEM's own crisis-flow/referral output —
    a brother-facilitated psychiatric intake contact, prompted by
    crisis-support information the patient recalls from an earlier
    session. This is additive to (never replaces) the persona's own two
    documented brother-contact events (`VP-003_first_visit_severe.md:72`,
    "3개월간 통화 2회") spent at S3 (a call) and S10 (a visit).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScenarioSession:
    """One scripted session's guideline content — design doc §2.5."""

    session_index: int  # 1-based
    day_offset: int  # days since session 1
    arc_mode: str  # "improvement_plateau" | "relapse_after_partial_improvement"
    phase_label: str  # "acute_engagement" | "response_consolidation" | "maintenance"
    state_descriptor_ko: str  # patient's state AT this date only
    inter_session_events_ko: list[str] = field(default_factory=list)  # since prior session
    # domain -> qualitative direction; DESIGN INTENT ONLY, never rendered
    # into injected text (see module docstring).
    symptom_targets: dict[str, str] = field(default_factory=dict)
    reveal_guidance_ko: str = ""  # what/how the patient discloses this session

    @property
    def scenario_pack_id(self) -> str:
        persona_id = self._persona_id_from_arc_mode()
        return f"{persona_id}_{self.arc_mode}_s{self.session_index:02d}"

    def _persona_id_from_arc_mode(self) -> str:
        # Both packs below are 1:1 (persona <-> arc_mode) in this mission —
        # this mapping is the same one §2.2 justifies; a future 3rd VP/arc
        # would extend this, not overload an existing mode string.
        return _ARC_MODE_TO_PERSONA[self.arc_mode]


_ARC_MODE_TO_PERSONA: dict[str, str] = {
    "improvement_plateau": "VP-001",
    "relapse_after_partial_improvement": "VP-003",
    "treatment_response_setback": "VP-002",
    "fluctuating_panic_recurrence": "VP-004",
    "stable_minimizing_slow_disclosure": "VP-010",
    "somatic_persistent_late_mood_disclosure": "VP-011",
    "aud_escalation_contemplation": "VP-012",
}


def _phase_for(session_index: int) -> str:
    """§2.3 cadence table: 1-4 acute_engagement, 5-7 response_consolidation,
    8-11 maintenance."""
    if session_index <= 4:
        return "acute_engagement"
    if session_index <= 7:
        return "response_consolidation"
    return "maintenance"


# §2.3 day-offset schedule (shared by both VPs, both arcs) — weekly during
# acute engagement, biweekly during response consolidation, monthly during
# maintenance; day 0 -> day 183 (~6.0 months).
_DAY_OFFSETS: list[int] = [0, 7, 14, 21, 35, 49, 63, 91, 122, 152, 183]


def render_scenario_guideline(
    session: ScenarioSession, n_sessions: int, simulated_date: str
) -> str:
    """Build the injected guideline text (design doc §2.5's exact
    template) — the harness passes ONLY this session's own rendered text
    into `f1._run_simulation(scenario_guideline=...)`, never the whole arc
    table (isolation invariant, test-proven in
    `tests/simulation/test_scenario_pack.py`)."""
    events = (
        "\n".join(f"  - {e}" for e in session.inter_session_events_ko)
        if session.inter_session_events_ko
        else "  - (지난 세션 이후 특별한 사건 없음)"
    )
    return (
        f"## 세션 시나리오 안내 (개발 검증용, {simulated_date}, "
        f"세션 {session.session_index}/{n_sessions})\n"
        f"- 현재 상태: {session.state_descriptor_ko}\n"
        f"- 지난 세션 이후 있었던 일:\n{events}\n"
        f"- 이번 세션에서 자연스럽게 드러낼 내용: {session.reveal_guidance_ko}\n\n"
        "주의: 당신은 앞으로 무슨 일이 있을지 알지 못합니다. 오직 지금까지 일어난 일과 "
        "현재 상태만을 바탕으로 자연스럽게 답하세요."
    )


# ── VP-001 — improvement_plateau (design doc §2.4, re-anchored per
#    ADR-036 item 6: S1 PHQ-9 target = persona-documented mild baseline
#    ~7, not the previously-considered ~13 EXP-019 over-triage artifact) ──

_VP001_STATES: list[str] = [
    # S1 — baseline
    "3주 전부터 시작된 불안감과 수면 문제로 처음 상담을 받으러 왔습니다. 잠들기까지 "
    "1~2시간이 걸리고 새벽에 2~3회 깨며, 회사 프로젝트 데드라인 압박이 주된 스트레스원입니다. "
    "식욕이 약간 줄었고 퇴근 후에는 아무것도 하기 싫은 무기력함이 있습니다.",
    # S2
    "프로젝트 데드라인을 무사히 넘기고 나서 확연히 안도감을 느끼고 있습니다. 수면 시간이 "
    "조금씩 늘어 5~6시간 정도 자기 시작했고, 잠들기까지 걸리는 시간도 예전보다 짧아졌습니다. "
    "다만 아직 완전히 편해지지는 않았습니다.",
    # S3
    "지난주보다 조금 더 편안해졌습니다. 2주 만에 처음으로 주말 요가 수업에 한 번 다녀왔고, "
    "식욕도 조금씩 돌아오는 느낌입니다. 그래도 가끔 일 생각이 나면 여전히 긴장됩니다.",
    # S4
    "이번 주는 확실히 컨디션이 좋습니다. 수면이 6~7시간으로 늘었고, 업무에서도 실수가 "
    "줄었습니다. 회사에서 좋은 평가를 받아서 기분이 한결 나아졌습니다.",
    # S5 — plateau/wobble
    "새로운 프로젝트를 맡게 되면서 다시 약간 긴장되고 있습니다. 예전만큼 심하지는 않지만 "
    "수면이 다시 조금 불편해졌고, 은근히 걱정되는 마음이 듭니다. 그래도 예전에 비하면 훨씬 "
    "낫다는 걸 스스로도 느낍니다.",
    # S6
    "새 프로젝트에 적응하며 지난번 배운 방법들을 써보고 있습니다. 스트레스 받을 때 운동을 "
    "하거나 동료와 이야기를 나누면 확실히 도움이 됩니다.",
    # S7
    "새 프로젝트의 중요한 마일스톤을 성공적으로 마쳤습니다. 다시 컨디션이 좋아졌고, 주변 "
    "사람들과의 관계도 든든하게 느껴집니다.",
    # S8 — maintenance begins
    "유지기에 접어든 느낌입니다. 가끔 스트레스가 있어도 전반적으로 안정적입니다. 지난 "
    "주말에는 짧은 여행도 다녀왔습니다.",
    # S9
    "한 달 동안 큰 변화 없이 잘 지냈습니다. 하루 정도 잠을 설친 날이 있었지만 그 외에는 "
    "6~7시간씩 꾸준히 자고 있습니다.",
    # S10
    "특별한 사건 없이 안정적으로 지내고 있습니다. 회사 업무도 무리 없이 소화하고 있습니다.",
    # S11 — final
    "새로운 작은 마감이 있었지만 예전처럼 크게 흔들리지 않고 잘 넘겼습니다. 전반적으로 처음 "
    "상담받으러 왔을 때와 비교하면 훨씬 편안해졌다고 느낍니다.",
]

_VP001_EVENTS: list[list[str]] = [
    [],
    ["프로젝트 데드라인을 무사히 마감함", "팀원들과 작은 회식 자리를 가짐"],
    ["2주 만에 요가 수업에 한 번 참석함", "식욕이 조금씩 정상으로 돌아옴"],
    ["업무 성과 평가에서 긍정적인 피드백을 받음"],
    ["새 프로젝트 킥오프 — 빠듯하지만 감당할 수 있는 일정"],
    ["스트레스 받는 주간에 운동/동료와의 대화로 대처함"],
    ["새 프로젝트 마일스톤을 성공적으로 완료함"],
    ["짧은 주말 여행을 다녀옴"],
    ["하루 정도 잠을 설친 날이 있었음 (그 외에는 특별한 일 없음)"],
    ["이번 달은 특별한 사건 없이 지나감"],
    ["작은 업무 마감이 있었지만 무리 없이 처리함"],
]

_VP001_REVEALS: list[str] = [
    "첫 상담이므로 조심스럽게, 그러나 질문을 받으면 솔직하게 증상을 설명하세요. 정신과가 "
    "처음이라 다소 어색해하되 협조적인 태도를 유지하세요.",
    "지난 상담 이후 좋아진 부분(수면, 기분)을 자연스럽게 언급하되, 아직 완전히 회복된 것은 "
    "아니라는 뉘앙스를 유지하세요.",
    "회복 초기 단계임을 자연스럽게 드러내세요. 운동을 다시 시작한 것에 대해 스스로도 "
    "뿌듯해하는 느낌을 담아 표현하세요.",
    "눈에 띄게 좋아진 상태를 자신감 있게 말하세요. 다만 여전히 가끔 걱정이 스치는 정도의 "
    "잔여 증상은 자연스럽게 언급해도 됩니다.",
    "완전히 예전 수준으로 돌아간 것이 아니라 '살짝 다시 불안해지는' 느낌을 표현하세요. "
    "예전 경험과 비교해 '그때만큼 심하진 않다'는 뉘앙스를 자연스럽게 섞으세요.",
    "스스로 터득한 대처 방법을 사용하고 있다는 점을 담담하게 이야기하세요. 자기 효능감이 "
    "느껴지는 톤으로 답하세요.",
    "회복이 다시 자리잡은 느낌을 자연스럽게 표현하세요.",
    "전반적으로 안정된 상태를 짧고 담백하게 이야기하세요. 특별히 새로운 걱정거리를 꺼내지 "
    "마세요.",
    "안정적인 한 달을 짧게 요약하듯 말하세요. 하루 정도의 사소한 컨디션 저하는 대수롭지 "
    "않게 언급하세요.",
    "간결하게 '잘 지내고 있다'는 취지로 답하세요.",
    "6개월 전과 비교했을 때의 변화를 스스로 되짚어보는 톤으로, 자연스럽게 회고하듯 말하세요.",
]

# Design-intent (never hard-pinned, never rendered) — re-anchored per
# ADR-036 item 6 from the persona's documented mild PHQ-9 baseline (~7).
_VP001_PHQ9_TARGETS = [
    "~7", "~6", "~5", "~4", "~6 (non-monotonic uptick)", "~4", "~3", "~3", "~3", "~2", "~3",
]
_VP001_CTRS_TARGETS = ["5", "5", "5", "5", "5", "5", "5", "5", "5", "5", "5"]


def _build_pack(
    arc_mode: str,
    states: list[str],
    events: list[list[str]],
    reveals: list[str],
    phq9_targets: list[str],
    ctrs_targets: list[str],
) -> tuple[ScenarioSession, ...]:
    lengths = {len(states), len(events), len(reveals), len(phq9_targets), len(ctrs_targets)}
    assert lengths == {11}
    sessions = tuple(
        ScenarioSession(
            session_index=i + 1,
            day_offset=_DAY_OFFSETS[i],
            arc_mode=arc_mode,
            phase_label=_phase_for(i + 1),
            state_descriptor_ko=states[i],
            inter_session_events_ko=list(events[i]),
            symptom_targets={"PHQ-9": phq9_targets[i], "CTRS": ctrs_targets[i]},
            reveal_guidance_ko=reveals[i],
        )
        for i in range(11)
    )
    ids = [s.scenario_pack_id for s in sessions]
    if len(set(ids)) != len(ids):
        raise AssertionError(f"scenario_pack_id collision in {arc_mode} pack: {ids}")
    return sessions


VP_001_IMPROVEMENT_PLATEAU: tuple[ScenarioSession, ...] = _build_pack(
    "improvement_plateau", _VP001_STATES, _VP001_EVENTS, _VP001_REVEALS,
    _VP001_PHQ9_TARGETS, _VP001_CTRS_TARGETS,
)


# ── VP-003 — relapse_after_partial_improvement (design doc §2.4, S8 gains
#    a system-crisis-flow-consequence event per ADR-036 item 5) ──────────

_VP003_STATES: list[str] = [
    # S1 — baseline, crisis-adjacent
    "3개월 전 구조조정으로 퇴사한 이후 극심한 우울감과 무기력이 지속되고 있습니다. 거의 매일 "
    "'사라지고 싶다'는 생각이 들지만 구체적인 계획은 없습니다. 하루 대부분을 방에 누워 지내고, "
    "거의 매일 소주를 마십니다.",
    # S2
    "지난 상담에서 처음으로 힘든 마음을 털어놓고 나서 아주 조금은 후련한 느낌이 있었습니다. "
    "그래도 여전히 거의 매일 사라지고 싶다는 생각이 들고, 하루하루가 똑같이 힘듭니다.",
    # S3
    "형에게서 짧게 전화가 한 통 왔습니다. 별다른 이야기는 아니었지만 며칠간은 기분이 조금 "
    "나아졌습니다.",
    # S4
    "몇 군데 구직 사이트에 이력서를 넣어봤습니다. 큰 의욕은 없었지만 뭐라도 해야 할 것 같아서 "
    "했습니다. 잠도 아주 조금 나아져서 3시간 반 정도는 잡니다.",
    # S5 — early warning uptick
    "실업급여가 한 달 후면 끝난다는 통지를 받았습니다. 그 생각을 하면 다시 숨이 막히는 느낌이 "
    "듭니다. 며칠 사이 다시 마음이 많이 무거워졌습니다.",
    # S6 — relapse trigger
    "이번 주에 실업급여가 완전히 끊겼습니다. 앞으로 어떻게 살아야 할지 막막하고, 사라지고 "
    "싶다는 생각이 예전보다 더 자주, 더 강하게 듭니다. 술도 더 늘었습니다.",
    # S7 — arc peak
    "일도 없고 수입도 없고, 연락하는 사람도 없는 상태가 이어지고 있습니다. 지금이 가장 힘든 "
    "시기인 것 같습니다.",
    # S8 — minimal stabilization + system-prompted brother contact
    "긴급 생계 지원을 신청했습니다. 그리고 지난 상담에서 안내받았던 위기 지원 정보가 계속 "
    "마음에 남아서, 처음으로 형에게 먼저 연락을 했습니다. 형이 정신과 진료를 같이 알아봐 "
    "주기로 했습니다.",
    # S9
    "짧은 시간이지만 파트타임 일을 시작했습니다. 힘들지만 그래도 하루의 리듬이 조금 생겼습니다. "
    "형과도 가끔 연락을 주고받고 있습니다.",
    # S10
    "형이 한 번 집에 찾아왔습니다. 오랜만에 얼굴을 보니 어색했지만 나쁘지 않았습니다. 전반적으로 "
    "아주 조금씩 나아지고 있는 것 같습니다.",
    # S11 — final, partial/incomplete recovery
    "요즘은 사라지고 싶다는 생각이 매일은 아니고 가끔 듭니다. 여전히 완전히 괜찮아진 것은 "
    "아니지만, 6개월 전보다는 조금이라도 버틸 수 있는 것 같습니다.",
]

_VP003_EVENTS: list[list[str]] = [
    [],
    ["아무에게도 연락이 없었고, 아무도 만나지 않음"],
    ["형에게서 짧은 전화가 한 번 옴"],
    ["몇 군데 구직 사이트에 이력서를 지원함"],
    ["실업급여가 약 1개월 후 종료된다는 통지를 받음"],
    ["이번 주 실업급여가 완전히 종료됨"],
    ["일자리도, 수입도, 연락하는 사람도 없는 상태가 한 달째 이어짐"],
    [
        "긴급 복지 지원(생계 지원)을 신청함",
        "지난 상담에서 안내받은 위기 지원 정보를 계기로 처음으로 형에게 먼저 연락함 — "
        "형이 정신과 진료 예약을 함께 알아봐 주기로 함",
    ],
    ["파트타임 일을 시작함", "형과 간헐적으로 연락을 주고받기 시작함"],
    ["형이 집에 한 번 방문함"],
    ["이번 달은 특별한 위기 없이 지나감"],
]

_VP003_REVEALS: list[str] = [
    "짧고 단편적인 답변으로, 에너지가 없는 느낌을 표현하세요. 자살 사고를 물으면 숨기지 말고 "
    "'사라지고 싶다'는 표현으로 자연스럽게 드러내되, 구체적 계획은 없다고 명확히 답하세요.",
    "지난 상담에서 말하고 나서의 미묘한 안도감을 아주 살짝만 표현하세요. 여전히 고통이 크다는 "
    "점이 더 우선되게 답하세요.",
    "형과의 통화에 대해 물으면 담담하게 이야기하되, 관계가 소원하다는 느낌은 유지하세요 "
    "('짐이 되기 싫어서' 연락을 먼저 하지는 않는다는 태도).",
    "작은 행동 변화(구직 지원)를 담담하게, 큰 기대 없이 이야기하세요. '해봤자 뭐 하나' 싶은 "
    "회의적인 톤을 유지하세요.",
    "구체적으로 물으면 실업급여 종료 통지에 대한 불안을 드러내세요. 재정적 압박이 다시 크게 "
    "다가온다는 점을 강조하세요.",
    "재정 파탄에 대한 공포와 자살 사고의 강도가 다시 초반 수준으로 되돌아간 느낌을 표현하세요. "
    "구체적 계획은 여전히 없다고 답하되, 사고의 빈도/강도가 늘었음을 분명히 드러내세요.",
    "가장 고립되고 힘든 상태를 표현하세요. 침묵과 짧은 답변, 회피적 태도('몰라요', '그냥요')를 "
    "더 자주 사용하세요.",
    "형에게 먼저 연락했다는 사실을 다소 어색해하면서도 이야기하세요 ('짐이 되기 싫었는데... "
    "그래도 한번 해봤어요' 정도의 톤). 상담에서 안내받은 위기 지원 정보가 연락을 결심하는 데 "
    "도움이 됐다는 점을 자연스럽게 언급하되, 과장하지 마세요 — 여전히 조심스럽고 확신 없는 "
    "태도를 유지하세요.",
    "여전히 힘들다는 기조는 유지하되, 아주 조금씩 나아지는 부분(일, 형과의 연락)을 담담하게 "
    "언급하세요. 과도한 낙관은 피하세요.",
    "가족과의 재연결이 조금씩 쌓이고 있다는 느낌을 표현하되, 여전히 완전히 편해진 것은 아니라는 "
    "뉘앙스를 유지하세요.",
    "완전한 회복이 아니라 부분적이고 불완전한 회복을 표현하세요 — 자살 사고가 완전히 사라진 "
    "것이 아니라 빈도가 줄었을 뿐이라는 점을 명확히 하세요.",
]

_VP003_PHQ9_TARGETS = [
    "~23", "~20", "~18", "~17", "~19 (early warning uptick)", "~23", "~24 (arc peak)",
    "~20", "~17", "~15", "~14",
]
_VP003_CTRS_TARGETS = ["2-3", "3", "3", "3", "3", "2", "2", "3", "3", "3-4", "4"]

VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT: tuple[ScenarioSession, ...] = _build_pack(
    "relapse_after_partial_improvement", _VP003_STATES, _VP003_EVENTS, _VP003_REVEALS,
    _VP003_PHQ9_TARGETS, _VP003_CTRS_TARGETS,
)


# Imported here (not at module top) to avoid a circular import: each of these 5 pack modules
# does `from tests.simulation.scenario_pack import ScenarioSession`, which requires this module
# to have already fully defined `ScenarioSession` (and populated `_ARC_MODE_TO_PERSONA` above)
# before they load.
from tests.simulation.scenario_packs.vp002_treatment_response_setback import (  # noqa: E402
    VP_002_TREATMENT_RESPONSE_SETBACK,
)
from tests.simulation.scenario_packs.vp004_fluctuating_panic_recurrence import (  # noqa: E402
    VP_004_FLUCTUATING_PANIC_RECURRENCE,
)
from tests.simulation.scenario_packs.vp010_stable_minimizing_slow_disclosure import (  # noqa: E402
    VP_010_STABLE_MINIMIZING_SLOW_DISCLOSURE,
)
from tests.simulation.scenario_packs.vp011_somatic_persistent_late_mood_disclosure import (  # noqa: E402
    VP_011_SOMATIC_PERSISTENT_LATE_MOOD_DISCLOSURE,
)
from tests.simulation.scenario_packs.vp012_aud_escalation_contemplation import (  # noqa: E402
    VP_012_AUD_ESCALATION_CONTEMPLATION,
)

_SCENARIO_PACKS: dict[str, tuple[ScenarioSession, ...]] = {
    "VP-001": VP_001_IMPROVEMENT_PLATEAU,
    "VP-003": VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT,
    "VP-002": VP_002_TREATMENT_RESPONSE_SETBACK,
    "VP-004": VP_004_FLUCTUATING_PANIC_RECURRENCE,
    "VP-010": VP_010_STABLE_MINIMIZING_SLOW_DISCLOSURE,
    "VP-011": VP_011_SOMATIC_PERSISTENT_LATE_MOOD_DISCLOSURE,
    "VP-012": VP_012_AUD_ESCALATION_CONTEMPLATION,
}


def get_scenario_pack(persona_id: str) -> tuple[ScenarioSession, ...]:
    """Look up the named VP's scripted arc. Raises `KeyError` loudly for an
    unknown persona_id — never silently returns an empty/wrong pack."""
    if persona_id not in _SCENARIO_PACKS:
        raise KeyError(
            f"No scenario pack for persona_id={persona_id!r} — available: "
            f"{sorted(_SCENARIO_PACKS)}"
        )
    return _SCENARIO_PACKS[persona_id]
