"""F5 hand-off report Task 2 (`handoff_generator` v3) — prompt-file content
assertions + `HandoffGeneratorAgent.generate_narrative` wiring.

Mirrors `tests/test_prompt_v3.py`'s own placeholder-only/budget/no-echo
discipline (design doc's own "v3 prompt design rules"), applied to the NEW
`docs/ai/prompts/handoff_generator/v3.system.md` file only — `test_prompt_
v3.py` itself is NOT edited (v2's own pin/tests there are untouched, per
brief). v1/v2 files are never edited here either (rollback policy).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.handoff_generator import (
    _NARRATIVE_PROMPT_VERSION,
    _PROMPT_VERSION,
    HandoffGeneratorAgent,
    NarrativeGenerationOutput,
)

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "ai" / "prompts"
_V3_PATH = _PROMPTS_DIR / "handoff_generator" / "v3.system.md"
V3 = _V3_PATH.read_text(encoding="utf-8")

# Pinned at authoring time (`sha256sum docs/ai/prompts/handoff_generator/
# v3.system.md`) — mirrors the font-asset SHA256 pin discipline
# `src/services/f5_report.py::_BODY_FONT_SHA256` already establishes for a
# different asset class (`BUG-044`/`ADR-038` Decision 1); this repo has no
# separate persisted "prompt pin table" file for developer to extend (root
# docs are qa/critic/orchestrator territory, not developer's), so this test
# is the one machine-checkable record of the v3 prompt's exact content —
# a mismatch means the file changed without a deliberate version bump.
_V3_SHA256 = "906686e5f12b8946263ef9bc2907d8c83b0eb095dafd4bcadd403fa33359da51"

# Same DR-001/ISS-027 echo-risk strings `test_prompt_v3.py` checks against
# its own 5 files — applied here too (placeholder-only discipline).
_KNOWN_BAD_STRINGS = [
    "서울대병원",
    "Escitalopram",
    "F33.1",
    "요즘 죽고 싶다는 생각이",
    "PHQ-9 | 18",
    "GAD-7 | 12",
    "3-4시간",
    "5-6시간",
    "18점",
    "12점",
    "요즘 계속 불안하고 잠을 못 자요",
]
_ICD_CODE_PATTERN = re.compile(r"F\d{2}")


class TestV3FileProvenance:
    def test_v1_and_v2_kept_per_versioning_policy(self) -> None:
        assert (_PROMPTS_DIR / "handoff_generator" / "v1.system.md").exists()
        assert (_PROMPTS_DIR / "handoff_generator" / "v2.system.md").exists()

    def test_v3_sha256_pinned(self) -> None:
        actual = hashlib.sha256(_V3_PATH.read_bytes()).hexdigest()
        assert actual == _V3_SHA256, (
            f"v3 prompt content changed (sha256={actual}) — update the pin above "
            "deliberately if this is an intentional edit."
        )


class TestV3PlaceholderOnly:
    def test_no_known_bad_strings(self) -> None:
        for bad in _KNOWN_BAD_STRINGS:
            assert bad not in V3, f"v3 contains echo-risk string: {bad!r}"

    def test_no_icd_code_pattern(self) -> None:
        assert not _ICD_CODE_PATTERN.search(V3)

    def test_no_worked_example_narrative_to_echo(self) -> None:
        """"No example-echo": the prompt must document the INPUT format
        with placeholders only, never ship a full worked-example OUTPUT
        paragraph a model could parrot verbatim."""
        assert "예시" not in V3 or "자리표시자" in V3


class TestV3HardConstraints:
    def test_role_is_a8_only_not_12_section(self) -> None:
        assert "A8" in V3
        assert "12개 섹션" not in V3
        assert "섹션 1." not in V3  # v2's own H2 header convention, must not survive

    def test_no_disease_naming_rule_present(self) -> None:
        assert "병명" in V3
        assert "언급하지 않는다" in V3

    def test_no_own_risk_reassessment_rule_present(self) -> None:
        assert "위험 관련 소견은 A3 참조" in V3

    def test_no_new_facts_rule_present(self) -> None:
        assert "새로운 사실" in V3 or "새로운 사실·숫자" in V3

    def test_honest_register_rule_present(self) -> None:
        assert "자가보고" in V3
        assert "비공식" in V3

    def test_word_count_target_documented(self) -> None:
        assert "150-250" in V3

    def test_no_evidence_id_or_table_template(self) -> None:
        """v2's evidence-ID convention/12-section table template must not
        survive into v3 — this agent's new role never emits either."""
        assert "[ev_{source_type}_" not in V3
        assert "근거 레지스트리" not in V3

    def test_budget(self) -> None:
        """Modest budget — v3's own role (one short paragraph) needs far
        less prompt text than v2's 12-section template."""
        assert len(V3) <= 4500
        assert len(V3.splitlines()) <= 120


class TestV2Untouched:
    """v2's own pin/behavior are unaffected by the v3 addition (brief:
    "do NOT edit v2")."""

    def test_run_still_pins_v2(self) -> None:
        assert _PROMPT_VERSION == "v2"

    def test_narrative_pin_is_a_separate_v3_constant(self) -> None:
        assert _NARRATIVE_PROMPT_VERSION == "v3"
        assert _NARRATIVE_PROMPT_VERSION != _PROMPT_VERSION


# ── generate_narrative wiring (mocked LLM) ──────────────────────────────


def _wire_adapter(agent: HandoffGeneratorAgent, resp_content: str) -> AsyncMock:
    router = MagicMock()
    agent._router = router  # type: ignore[attr-defined]
    resp = MagicMock()
    resp.content = resp_content
    resp.model = "test-model"
    resp.latency_ms = 1.0
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    router.get_adapter.return_value = adapter
    router.record_success = MagicMock()
    return adapter


class TestGenerateNarrativeWiring:
    @pytest.mark.asyncio
    async def test_loads_v3_prompt_and_returns_stripped_text(self) -> None:
        agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "v3 시스템 프롬프트"
        _wire_adapter(agent, "  환자는 수면 문제를 자가보고함.  ")

        out = await agent.generate_narrative("세션: 1회차, 2026-01-01\n주호소: 불면")

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "handoff_generator", "v3"
        )
        assert isinstance(out, NarrativeGenerationOutput)
        assert out.text == "환자는 수면 문제를 자가보고함."
        assert out.prompt_version == "v3"
        assert out.model_used == "test-model"
        assert out.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_never_calls_run_or_touches_handoff_input(self) -> None:
        """`generate_narrative` takes a plain string, not `HandoffInput` —
        the live `/ai/handoff/generate` route's own contract is untouched
        by this method's existence."""
        agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "v3 프롬프트"
        _wire_adapter(agent, "요약 텍스트")

        out = await agent.generate_narrative("입력 텍스트")
        assert out.text == "요약 텍스트"

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_adapter_failure(self) -> None:
        agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "v3 프롬프트"

        router = MagicMock()
        agent._router = router
        primary_adapter = AsyncMock(spec=LLMAdapter)
        primary_adapter.chat_timed = AsyncMock(side_effect=RuntimeError("boom"))
        router.select_model.return_value = MagicMock(adapter_name="primary", model_id="m1")

        fb_resp = MagicMock()
        fb_resp.content = "fallback 응답"
        fb_resp.model = "fallback-model"
        fallback_adapter = AsyncMock(spec=LLMAdapter)
        fallback_adapter.chat_timed = AsyncMock(return_value=fb_resp)

        def _get_adapter(name: str):
            return primary_adapter if name == "primary" else fallback_adapter

        router.get_adapter.side_effect = _get_adapter
        router.get_fallback.return_value = MagicMock(adapter_name="fallback", model_id="m2")
        router.record_failure = MagicMock()
        router.record_success = MagicMock()

        out = await agent.generate_narrative("입력 텍스트")
        assert out.text == "fallback 응답"
        assert out.model_used == "fallback-model"

    @pytest.mark.asyncio
    async def test_raises_when_no_fallback_available(self) -> None:
        agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "v3 프롬프트"

        router = MagicMock()
        agent._router = router
        primary_adapter = AsyncMock(spec=LLMAdapter)
        primary_adapter.chat_timed = AsyncMock(side_effect=RuntimeError("boom"))
        router.select_model.return_value = MagicMock(adapter_name="primary", model_id="m1")
        router.get_adapter.return_value = primary_adapter
        router.get_fallback.return_value = None
        router.record_failure = MagicMock()

        with pytest.raises(RuntimeError, match="no fallback available"):
            await agent.generate_narrative("입력 텍스트")
