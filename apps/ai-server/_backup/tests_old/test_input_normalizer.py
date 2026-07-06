"""T1-F1-DEV-002: InputNormalizerAgent tests.

Tests schema validation, safety keyword preservation, LLM failure fallback,
and change log structure. No LLM calls — all mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.input_normalizer import (
    InputNormalizerAgent,
    _SAFETY_EXPRESSIONS,
)
from src.schemas.input_normalizer import (
    InputNormalizerInput,
    InputNormalizerOutput,
    NormalizationChange,
)


# ── Schema tests ────────────────────────────────────────────────────


class TestInputNormalizerSchemas:
    """Validate I/O schema fields and defaults."""

    def test_input_schema_fields(self):
        inp = InputNormalizerInput(
            session_id="s1",
            raw_text="테스트 입력",
            input_type="stt_transcript",
            dialect_hint="경상",
        )
        assert inp.raw_text == "테스트 입력"
        assert inp.input_type == "stt_transcript"
        assert inp.dialect_hint == "경상"

    def test_input_defaults(self):
        inp = InputNormalizerInput(session_id="s1", raw_text="test")
        assert inp.input_type == "user_text"
        assert inp.dialect_hint is None

    def test_output_defaults(self):
        out = InputNormalizerOutput()
        assert out.normalized_text == ""
        assert out.original_text == ""
        assert out.changes == []
        assert out.change_count == 0
        assert out.clinical_content_preserved is True
        assert out.risk_expressions_preserved is True

    def test_change_types(self):
        for t in ["stt_error", "colloquial", "dialect", "typo", "spacing"]:
            c = NormalizationChange(original="a", normalized="b", type=t)
            assert c.type == t

    def test_invalid_change_type_rejected(self):
        with pytest.raises(Exception):
            NormalizationChange(original="a", normalized="b", type="invalid_type")

    def test_input_type_ocr(self):
        inp = InputNormalizerInput(
            session_id="s1", raw_text="OCR 텍스트", input_type="ocr_document"
        )
        assert inp.input_type == "ocr_document"


# ── Agent logic tests ───────────────────────────────────────────────


def _make_agent() -> InputNormalizerAgent:
    """Create agent with mocked dependencies."""
    agent = InputNormalizerAgent.__new__(InputNormalizerAgent)
    agent._router = MagicMock()
    agent._prompt_loader = MagicMock()
    return agent


class TestSafetyKeywordPreservation:
    """Safety expressions must NEVER be lost during normalization."""

    def test_safety_expressions_defined(self):
        """Verify we have a substantial set of safety keywords."""
        assert len(_SAFETY_EXPRESSIONS) >= 20

    def test_verify_safety_preserves_when_present(self):
        """Expression in both original and normalized → True."""
        assert InputNormalizerAgent._verify_safety_expressions(
            "죽고 싶어요", "죽고 싶어요"
        )

    def test_verify_safety_detects_loss(self):
        """Expression in original but not in normalized → False."""
        assert not InputNormalizerAgent._verify_safety_expressions(
            "죽고 싶어요", "힘들어요"
        )

    def test_verify_safety_space_insensitive(self):
        """Space differences should not matter for safety check."""
        assert InputNormalizerAgent._verify_safety_expressions(
            "죽고싶어요", "죽고 싶어요"
        )
        assert InputNormalizerAgent._verify_safety_expressions(
            "손목을 긋고 싶어요", "손목을긋고 싶어요"
        )

    def test_verify_no_safety_keywords_returns_true(self):
        """Text without any safety keywords → True (nothing to lose)."""
        assert InputNormalizerAgent._verify_safety_expressions(
            "요즘 잠을 못 자요", "요즘 잠을 못 자요"
        )

    @pytest.mark.asyncio
    async def test_agent_rejects_when_safety_lost(self):
        """If LLM removes a safety expression, agent returns original."""
        agent = _make_agent()

        # Mock LLM returning text with safety expression removed
        mock_resp = MagicMock()
        mock_resp.content = '{"normalized_text": "힘들어요", "changes": []}'
        mock_resp.model = "test"

        mock_adapter = AsyncMock()
        mock_adapter.chat_timed = AsyncMock(return_value=mock_resp)

        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=True, supports_json_object=True,
        )
        agent._router.get_adapter.return_value = mock_adapter
        agent._prompt_loader.load_system_prompt.return_value = "test prompt"

        inp = InputNormalizerInput(
            session_id="s1",
            raw_text="죽고 싶어요",
            input_type="user_text",
        )
        result = await agent.run(inp)

        # Should fallback to original
        assert result.normalized_text == "죽고 싶어요"
        assert result.risk_expressions_preserved is True
        assert "fallback" in result.reason_summary or "safety" in result.reason_summary


class TestLLMFailureFallback:
    """On LLM failure, agent must return original text unchanged."""

    @pytest.mark.asyncio
    async def test_llm_exception_returns_original(self):
        agent = _make_agent()

        # Mock LLM raising an exception
        mock_adapter = AsyncMock()
        mock_adapter.chat_timed = AsyncMock(side_effect=RuntimeError("LLM down"))

        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        agent._router.get_adapter.return_value = mock_adapter
        agent._prompt_loader.load_system_prompt.return_value = "test prompt"

        inp = InputNormalizerInput(session_id="s1", raw_text="원본 텍스트")
        result = await agent.run(inp)

        assert result.normalized_text == "원본 텍스트"
        assert result.original_text == "원본 텍스트"
        assert result.changes == []
        assert result.change_count == 0

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        agent = _make_agent()
        inp = InputNormalizerInput(session_id="s1", raw_text="")
        result = await agent.run(inp)

        assert result.normalized_text == ""
        assert result.original_text == ""
        assert result.change_count == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty(self):
        agent = _make_agent()
        inp = InputNormalizerInput(session_id="s1", raw_text="   ")
        result = await agent.run(inp)

        assert result.normalized_text == ""
        assert result.change_count == 0


class TestSuccessfulNormalization:
    """Successful LLM normalization with proper change log."""

    @pytest.mark.asyncio
    async def test_successful_normalization(self):
        agent = _make_agent()

        mock_resp = MagicMock()
        mock_resp.content = '''{
            "normalized_text": "요즘 잠을 못 자요",
            "changes": [
                {
                    "original": "몬자요",
                    "normalized": "못 자요",
                    "type": "stt_error",
                    "position": {"start": 4, "end": 7}
                }
            ]
        }'''
        mock_resp.model = "solar-pro3"

        mock_adapter = AsyncMock()
        mock_adapter.chat_timed = AsyncMock(return_value=mock_resp)

        agent._router.select_model.return_value = MagicMock(
            adapter_name="solar-pro3", model_id="solar-pro3",
            supports_json_schema=True, supports_json_object=True,
        )
        agent._router.get_adapter.return_value = mock_adapter
        agent._prompt_loader.load_system_prompt.return_value = "test prompt"

        inp = InputNormalizerInput(
            session_id="s1",
            raw_text="요즘 몬자요",
            input_type="stt_transcript",
        )
        result = await agent.run(inp)

        assert result.normalized_text == "요즘 잠을 못 자요"
        assert result.original_text == "요즘 몬자요"
        assert result.change_count == 1
        assert result.changes[0].type == "stt_error"
        assert result.changes[0].original == "몬자요"
        assert result.model_used == "solar-pro3"
        assert result.clinical_content_preserved is True
