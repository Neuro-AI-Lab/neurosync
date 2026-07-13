"""BUG-023 fix verification: `InputNormalizerAgent._normalize`'s
`prompts_degraded=True` must survive a COMPOUND failure (prompt-missing +
downstream JSON parse failure).

Root cause (pre-fix, `error.md` BUG-023): `_normalize` set the local
`prompts_degraded = True` after a `FileNotFoundError` on prompt load, but
never caught its own subsequent `json.loads(resp.content)` failure — that
exception propagated out of `_normalize` entirely to `run()`'s outer
`except Exception: result = self._safe_fallback(inp)` (no `prompts_degraded`
kwarg), discarding the local flag.

Fix (PLAN-2026-W28-Q W2): `_normalize` now catches its own parse failure
locally and returns `self._safe_fallback(inp, ..., prompts_degraded=
prompts_degraded)` from within itself, mirroring the existing
safety-expression-loss path a few lines below.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.input_normalizer import InputNormalizerAgent
from src.schemas.input_normalizer import InputNormalizerInput


def _agent_with_missing_prompt_and_bad_json(bad_json: str) -> InputNormalizerAgent:
    agent = InputNormalizerAgent.__new__(InputNormalizerAgent)
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.side_effect = FileNotFoundError("no prompt file")

    router = MagicMock()
    selection = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    router.select_model.return_value = selection
    adapter = MagicMock()
    adapter.chat_timed = AsyncMock(return_value=MagicMock(content=bad_json, model="test"))
    router.get_adapter.return_value = adapter
    router.record_success = MagicMock()
    agent._router = router
    return agent


@pytest.mark.asyncio
async def test_compound_failure_still_reports_prompts_degraded_true():
    """The exact BUG-023 repro: missing prompt file (sets the local flag)
    AND a downstream JSON parse failure (previously discarded it)."""
    agent = _agent_with_missing_prompt_and_bad_json("NOT VALID JSON {{{")

    out = await agent.run(InputNormalizerInput(
        session_id="t-bug023", raw_text="테스트 문장", input_type="user_text",
    ))

    assert out.prompts_degraded is True
    # Safe fallback semantics preserved (BUG-023 is a flag-visibility defect,
    # not an unsafe-output defect).
    assert out.normalized_text == "테스트 문장"
    assert out.original_text == "테스트 문장"


@pytest.mark.asyncio
async def test_clean_prompt_with_downstream_parse_failure_reports_false():
    """Contrast case: a clean prompt load + a downstream parse failure
    correctly reports prompts_degraded=False (the prompt itself loaded
    fine) — the fix must not over-correct into always-True."""
    agent = InputNormalizerAgent.__new__(InputNormalizerAgent)
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "정규화 프롬프트"

    router = MagicMock()
    selection = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    router.select_model.return_value = selection
    adapter = MagicMock()
    adapter.chat_timed = AsyncMock(
        return_value=MagicMock(content="NOT VALID JSON {{{", model="test")
    )
    router.get_adapter.return_value = adapter
    router.record_success = MagicMock()
    agent._router = router

    out = await agent.run(InputNormalizerInput(
        session_id="t-bug023-clean", raw_text="테스트 문장 2", input_type="user_text",
    ))

    assert out.prompts_degraded is False


@pytest.mark.asyncio
async def test_degraded_prompt_with_successful_parse_still_reports_true():
    """Contrast case: the common (non-compound) degraded-prompt path is
    unaffected by this fix — still correctly True on a successful call."""
    agent = _agent_with_missing_prompt_and_bad_json(
        '{"normalized_text": "테스트 문장 3", "changes": []}'
    )

    out = await agent.run(InputNormalizerInput(
        session_id="t-bug023-degraded-ok", raw_text="테스트 문장 3", input_type="user_text",
    ))

    assert out.prompts_degraded is True
    assert out.normalized_text == "테스트 문장 3"
