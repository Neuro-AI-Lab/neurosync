"""REV-023 ruling 4 (binding atomicity constraint) + qa detection procedure
#6 (`_archive/plans/validation_plan_f1f2_continuous.md` §6): greeting-coupling
regression.

`f2.py`'s `_infer_is_first_visit` used to substring-match F1's hardcoded
turn-0 greeting (`_REVISIT_GREETING_MARKER = "지난번 상담 기록을 확인했습니다"`).
Dialogue v3's autonomous turn-0 greeting (`docs/ai/prompts/dialogue/
v3.system.md`) removes that fixed string — the marker match would silently
stop working, not fail loud, corrupting F2's first-visit/revisit inference.

PLAN-2026-W28-Q W2 fix: F2 now consumes F1's persisted `is_revisit` field
first, falling back to the legacy marker match ONLY for artifacts that
predate the field. This test asserts F2's inference is correct on
v3-era artifacts (real `is_revisit` field, NO marker string present in the
turn-0 greeting) — the exact scenario REV-023 ruling 4 requires landing
atomically with dialogue v3, in the SAME commit.
"""

from __future__ import annotations

from src.f2 import _infer_is_first_visit

_V3_GREETING_FIRST_VISIT = (
    "안녕하세요! 오늘 대화를 통해 편하게 이야기 나눠요. "
    "요즘 가장 신경 쓰이는 부분이 있다면 편하게 말씀해 주시겠어요?"
)
_V3_GREETING_REVISIT = (
    "안녕하세요! 다시 뵙게 되어 반갑습니다. 지난번에 이어서 요즘은 어떻게 지내고 "
    "계신지 편하게 말씀해 주시겠어요?"
)


def _artifact(*, turn0_response: str, is_revisit: bool | None) -> dict:
    data: dict = {"turns": [{"turn": 0, "agent_response": turn0_response}]}
    if is_revisit is not None:
        data["is_revisit"] = is_revisit
    return data


class TestV3EraArtifactsNoMarkerString:
    """The core atomicity check: NEITHER v3 greeting contains the legacy
    marker string — F2 must not silently default to "always first-visit"."""

    def test_marker_string_absent_from_both_v3_greetings(self) -> None:
        marker = "지난번 상담 기록을 확인했습니다"
        assert marker not in _V3_GREETING_FIRST_VISIT
        assert marker not in _V3_GREETING_REVISIT

    def test_first_visit_field_true_infers_first_visit(self) -> None:
        data = _artifact(turn0_response=_V3_GREETING_FIRST_VISIT, is_revisit=False)
        assert _infer_is_first_visit(data) is True

    def test_revisit_field_true_infers_not_first_visit(self) -> None:
        """The atomicity-critical case: a v3 revisit session, greeting has
        NO marker string, but is_revisit=True is persisted — F2 must still
        correctly infer is_first_visit=False."""
        data = _artifact(turn0_response=_V3_GREETING_REVISIT, is_revisit=True)
        assert _infer_is_first_visit(data) is False


class TestLegacyArtifactsFallback:
    """Documented fallback for pre-W2 artifacts lacking `is_revisit`."""

    def test_legacy_marker_present_infers_not_first_visit(self) -> None:
        legacy_greeting = (
            "안녕하세요! 저는 정신건강 사전문진을 도와드리는 AI 상담 도우미입니다.\n\n"
            "지난번 상담 기록을 확인했습니다. 지난번에 '불면' 문제로 상담하셨습니다.\n\n"
            "지난번 이후로 상태가 어떻게 변했는지 편하게 말씀해 주세요."
        )
        data = _artifact(turn0_response=legacy_greeting, is_revisit=None)
        assert "is_revisit" not in data
        assert _infer_is_first_visit(data) is False

    def test_legacy_no_marker_no_field_defaults_first_visit(self) -> None:
        data = _artifact(turn0_response="안녕하세요! 오늘 무엇을 도와드릴까요?", is_revisit=None)
        assert _infer_is_first_visit(data) is True

    def test_field_takes_priority_over_marker_when_both_present(self) -> None:
        """A v3-era artifact could (rarely) still contain the marker
        substring by coincidence — the persisted field must win, never the
        substring match, once the field exists."""
        data = _artifact(
            turn0_response="지난번 상담 기록을 확인했습니다 (우연의 일치).",
            is_revisit=False,
        )
        assert _infer_is_first_visit(data) is True
