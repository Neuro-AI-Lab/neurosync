"""T1-F1-DEV-017: clinical_slot prompt v2 (anti-echo) validation.

The 2026-07-03 incident: v1's realistic example values were echoed verbatim
into slot values. v2 must contain NO plausible clinical strings, only
unmistakably synthetic placeholders, and the agent must request v2.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.clinical_slot import PROMPT_VERSION, ClinicalSlotAgent
from src.schemas.clinical_slot import ClinicalSlotInput

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "ai" / "prompts"
_V1_PATH = _PROMPTS_DIR / "clinical_slot" / "v1.system.md"
_V2_PATH = _PROMPTS_DIR / "clinical_slot" / "v2.system.md"

# Realistic example strings from v1 that were echoed into the 07-03 run.
_V1_REALISTIC_STRINGS = [
    "정신과 진료 경험 없음",
    "진단받은 신체 질환 없음",
    "자살/자해 사고 명시적 부인",
    "잠을 못 자고, 불안감이 심하다",
    "주 1-2회 맥주 1캔",
    "어머니와 주 2회 통화",
    "말투 차분, 피로감 관찰됨",
    "직장 스트레스가 계기",
]

_REQUIRED_RULES = [
    "묻고 답하지 않은 슬롯은 반드시 null",
    "예시/템플릿 문구를 출력하지 않는다",
    "risk_assessment",
    "추론",
]


class TestV2PromptFile:
    def test_v1_kept_per_versioning_policy(self):
        assert _V1_PATH.exists(), "v1 must be kept (versioning policy)"

    def test_v2_exists(self):
        assert _V2_PATH.exists()

    def test_v2_contains_no_realistic_clinical_strings(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        for s in _V1_REALISTIC_STRINGS:
            assert s not in content, f"v2 must not contain plausible value: {s!r}"

    def test_v2_uses_synthetic_placeholders(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        assert "<환자가 실제로 말한" in content

    def test_v2_contains_required_rules(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        for rule in _REQUIRED_RULES:
            assert rule in content, f"v2 missing rule text: {rule!r}"

    def test_v2_keeps_all_12_keys(self):
        from src.agents.clinical_slot import ALL_SLOT_KEYS
        content = _V2_PATH.read_text(encoding="utf-8")
        for key in ALL_SLOT_KEYS:
            assert key in content, f"v2 missing slot key: {key}"

    def test_v2_risk_never_inferred_rule(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        assert "risk_assessment는 절대 추론하지 않는다" in content


class TestAgentRequestsV2:
    def test_prompt_version_constant(self):
        assert PROMPT_VERSION == "v2"

    @pytest.mark.asyncio
    async def test_agent_loads_v2_and_reports_v2(self):
        agent = ClinicalSlotAgent.__new__(ClinicalSlotAgent)
        agent._router = MagicMock()
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "슬롯을 추출하세요."

        resp = MagicMock()
        resp.content = "{}"
        resp.model = "test-model"
        resp.latency_ms = 1.0
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.chat_timed = AsyncMock(return_value=resp)

        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        agent._router.get_adapter.return_value = adapter
        agent._router.record_success = MagicMock()

        out = await agent.run(ClinicalSlotInput(
            session_id="t",
            conversation_history=[{"role": "user", "content": "hi"}],
        ))

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "clinical_slot", "v2"
        )
        assert out.prompt_version == "v2"
