"""Scripted patient + safety-matrix scenario validation (no LLM).

Verifies deterministic playback/branching and that every SM scenario file is
loadable with expectations the evaluator understands.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.f1 import CRISIS_RESPONSE, F1Result, F1TurnLog
from src.safety_matrix import (
    SCENARIOS_DIR,
    evaluate_expectations,
    list_scenario_ids,
    load_scenario,
)
from tests.simulation.scripted_patient import ScriptedPatient

_EXPECTED_SCENARIOS = {
    "SM-01", "SM-02", "SM-03", "SM-04a", "SM-04b", "SM-05", "SM-06",
    # PLAN-2026-W28 C1 (prompt_redesign_v3.md §4.2, ISS-046): SM-07a (panic
    # idiom must NOT trigger crisis) + SM-07b (mandatory adversarial control —
    # genuine SI phrasing near the same idiom must still trigger crisis).
    "SM-07a", "SM-07b",
    # ADR-011 (REV-004 issue #1): SM-08a (negated burden-ideation family —
    # must NOT trigger crisis, rule 7) + SM-08b (mandatory adversarial
    # control — the affirmed 하한표 anchor phrase must trigger immediate
    # CTRS 2 crisis with no probe detour, ADR-010 rule 5).
    "SM-08a", "SM-08b",
}


class TestScriptedPatient:
    @pytest.mark.asyncio
    async def test_ordered_playback(self):
        p = ScriptedPatient(script=["첫 번째", "두 번째"], default_utterance="기본")
        assert await p.respond("질문 1") == "첫 번째"
        assert await p.respond("질문 2") == "두 번째"
        assert await p.respond("질문 3") == "기본"
        assert p.turns_played == 3

    @pytest.mark.asyncio
    async def test_step_branching_on_ai_keywords(self):
        p = ScriptedPatient(script=[
            "시작 발화",
            {
                "branches": [
                    {"keywords": ["계획"], "say": "계획은 없어요."},
                    {"keywords": ["가족"], "say": "가족 얘기요."},
                ],
                "default": "글쎄요.",
            },
        ])
        assert await p.respond("안녕하세요") == "시작 발화"
        assert await p.respond("혹시 구체적인 계획이 있으신가요?") == "계획은 없어요."

    @pytest.mark.asyncio
    async def test_step_branch_default_when_no_keyword(self):
        p = ScriptedPatient(script=[
            {"branches": [{"keywords": ["계획"], "say": "A"}], "default": "B"},
        ])
        assert await p.respond("잠은 어떠세요?") == "B"

    @pytest.mark.asyncio
    async def test_global_responders_after_exhaustion(self):
        p = ScriptedPatient(
            script=["시작"],
            responders=[
                {"keywords": ["술", "음주"], "say": "술은 안 마셔요."},
                {"keywords": ["가족"], "say": "가족 중에는 없어요."},
            ],
            default_utterance="음...",
        )
        await p.respond("안녕하세요")
        assert await p.respond("음주는 어떠세요?") == "술은 안 마셔요."
        assert await p.respond("가족분들 중에는요?") == "가족 중에는 없어요."
        assert await p.respond("날씨가 좋네요") == "음..."

    @pytest.mark.asyncio
    async def test_deterministic_replay(self):
        cfg = dict(
            script=["a"],
            responders=[{"keywords": ["x"], "say": "b"}],
            default_utterance="c",
        )
        msgs = ["hello", "x라고 했어요", "zzz"]
        out1 = [await ScriptedPatient(**cfg).respond(m) for m in [msgs[0]]]
        p1, p2 = ScriptedPatient(**cfg), ScriptedPatient(**cfg)
        r1 = [await p1.respond(m) for m in msgs]
        r2 = [await p2.respond(m) for m in msgs]
        assert r1 == r2 == ["a", "b", "c"]
        assert out1 == ["a"]

    def test_from_scenario(self):
        scenario = load_scenario("SM-04b")
        p = ScriptedPatient.from_scenario(scenario)
        assert p.persona_id == "SM-04b"
        assert p.script


class TestScenarioFiles:
    def test_all_eleven_scenarios_present(self):
        assert set(list_scenario_ids()) == _EXPECTED_SCENARIOS

    def test_scenarios_load_with_required_fields(self):
        for sid in list_scenario_ids():
            s = load_scenario(sid)
            assert s["id"] == sid
            assert isinstance(s.get("max_turns"), int)
            assert s["patient"].get("script") or s["patient"].get("responders")
            assert s["expectations"], f"{sid} has no expectations"

    def test_all_expectation_checks_are_known(self):
        """Every check name in every scenario must be understood by the
        evaluator (unknown checks report 'unknown check: ...')."""
        dummy = F1Result(session_id="d", persona_id=None, persona_name=None)
        for sid in list_scenario_ids():
            s = load_scenario(sid)
            checks = evaluate_expectations(dummy, s["expectations"])
            for c in checks:
                assert not str(c["actual"]).startswith("unknown check"), (
                    f"{sid}: evaluator does not know check '{c['check']}'"
                )

    def test_scenario_json_is_valid_utf8_json(self):
        for path in Path(SCENARIOS_DIR).glob("SM-*.json"):
            json.loads(path.read_text(encoding="utf-8"))


def _turn(turn: int, ctrs: int, crisis: bool = False, response: str = "r") -> F1TurnLog:
    return F1TurnLog(
        turn=turn, patient_message=f"m{turn}", safety_ctrs=ctrs,
        safety_risk="none", safety_crisis=crisis, safety_categories=[],
        safety_flagged=[], agent_response=response, slot_updates={},
        cumulative_slots={}, slot_coverage=0.0, latency_ms=0.0,
        timestamp=datetime.now().isoformat(),
    )


class TestExpectationEvaluator:
    def _crisis_result(self) -> F1Result:
        return F1Result(
            session_id="t", persona_id="SM-01", persona_name=None,
            total_turns=4, crisis_triggered=True, crisis_turn=4,
            turns=[_turn(0, 5), _turn(1, 5), _turn(2, 5), _turn(3, 4),
                   _turn(4, 2, crisis=True, response=CRISIS_RESPONSE)],
            session_ctrs=2,
        )

    def test_sm01_style_expectations_pass_on_crisis_result(self):
        checks = evaluate_expectations(
            self._crisis_result(),
            load_scenario("SM-01")["expectations"],
        )
        assert all(c["passed"] for c in checks), checks

    def test_crisis_expectation_fails_on_benign_result(self):
        benign = F1Result(
            session_id="t", persona_id="SM-01", persona_name=None,
            total_turns=4, turns=[_turn(0, 5)], session_ctrs=5,
        )
        checks = evaluate_expectations(
            benign, [{"check": "crisis_triggered", "equals": True}]
        )
        assert not checks[0]["passed"]

    def test_probe_checks(self):
        r = F1Result(
            session_id="t", persona_id="SM-04b", persona_name=None,
            total_turns=6, risk_floor=3, session_ctrs=3,
            turns=[_turn(0, 5)],
            probe_events=[
                {"type": "trigger", "turn": 2},
                {"type": "progress", "turn": 3},
                {"type": "deescalation", "turn": 4, "risk_assessment_written": True},
            ],
            final_slots=[{"key": "risk_assessment", "value": "사고 표현 + 계획 부인"}],
        )
        checks = evaluate_expectations(r, [
            {"check": "probe_triggered", "equals": True},
            {"check": "probe_deescalated", "equals": True},
            {"check": "risk_assessment_grounded", "equals": True},
            {"check": "risk_floor", "equals": 3},
            {"check": "crisis_triggered", "equals": False},
            {"check": "min_total_turns", "value": 3},
        ])
        assert all(c["passed"] for c in checks), checks

    def test_unknown_check_reported(self):
        r = F1Result(session_id="t", persona_id=None, persona_name=None)
        checks = evaluate_expectations(r, [{"check": "nonexistent_check"}])
        assert not checks[0]["passed"]
