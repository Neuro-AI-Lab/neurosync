"""BUG-021 fix verification: real `PromptLoader` + `PROMPTS_BASE_DIR`
resolution, at both the CLI-entry level (`resolve_prompts_base_dir`) and the
per-agent fallback-catch level (`AgentOutput.prompts_degraded`).

qa's W0 baseline note (carried into the W1 brief, verbatim): "the pytest
suite's mocked-prompt-loader design means it will never surface BUG-021-class
regressions itself — any W1 fix verification for BUG-021 needs a
CLI-script-level test (or a new pytest case that exercises real
`PromptLoader` + `PROMPTS_BASE_DIR` resolution), not just a green `uv run
pytest`." This file is that test: no mocked `PromptLoader`, no mocked
`os.environ` bookkeeping — every path in `TestResolvePromptsBaseDir` is
resolved by the real `resolve_prompts_base_dir` (`src/prompts/loader.py`)
against the real repo-root `docs/ai/prompts/` tree, and
`TestAgentPromptsDegradedFlag` drives a real `PromptLoader` through
`SafetyClassifierAgent.run()` (only the LLM adapter/router are mocked — the
same established pattern as `tests/test_safety_failclosed.py`).

Root cause (`error.md` BUG-021): the old guard
(``if not os.environ.get("PROMPTS_BASE_DIR"): os.environ[...] = default``)
only ever corrected a *missing* value. This repo's own live
`apps/ai-server/.env` carries `PROMPTS_BASE_DIR=docs/ai/prompts` — a
repo-root-relative value that does not resolve when cwd is `apps/ai-server`
(the documented invocation convention, `cd apps/ai-server && ...`), so the
old guard's `not os.environ.get(...)` check evaluated False and silently
let every prompt-driven agent degrade to its generic hardcoded fallback
prompt, with zero hard failure (REV-021's independent confirmation, filed
against the live `.env`).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.safety_classifier import PROMPT_VERSION, SafetyClassifierAgent
from src.f1 import PROJECT_ROOT
from src.prompts.loader import PromptLoader, resolve_prompts_base_dir
from src.schemas.safety import SafetyInput

_REAL_PROMPTS_DIR = PROJECT_ROOT / "docs" / "ai" / "prompts"

# The exact value REV-021 independently confirmed live in this repo's own
# `apps/ai-server/.env` — the real-world trigger for BUG-021, not a
# hypothetical one.
_LIVE_ENV_RELATIVE_VALUE = "docs/ai/prompts"


class TestResolvePromptsBaseDirFixture:
    def test_real_prompts_dir_sanity(self) -> None:
        """Fixture isn't stale: the repo-root prompts tree really exists."""
        assert _REAL_PROMPTS_DIR.is_dir()
        assert (_REAL_PROMPTS_DIR / "safety_classifier" / f"{PROMPT_VERSION}.system.md").is_file()


class TestResolvePromptsBaseDirUnset:
    def test_unset_resolves_to_default_and_real_loader_loads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unset -> default to {project_root}/docs/ai/prompts (pre-existing
        behavior, preserved by the BUG-021 fix)."""
        monkeypatch.delenv("PROMPTS_BASE_DIR", raising=False)

        resolved = resolve_prompts_base_dir(PROJECT_ROOT)

        assert resolved == _REAL_PROMPTS_DIR.resolve()
        # BUG-021 (b): the guard rewrites os.environ so every later
        # Settings()/PromptLoader construction in-process sees it.
        assert os.environ["PROMPTS_BASE_DIR"] == str(resolved)

        content = PromptLoader(resolved).load_system_prompt(
            "safety_classifier", PROMPT_VERSION
        )
        assert len(content) > 0


class TestResolvePromptsBaseDirCorrectPath:
    def test_correct_absolute_path_resolves_and_real_loader_loads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Set-and-correct (absolute) -> used as-is, real prompt loads."""
        monkeypatch.setenv("PROMPTS_BASE_DIR", str(_REAL_PROMPTS_DIR))

        resolved = resolve_prompts_base_dir(PROJECT_ROOT)

        assert resolved == _REAL_PROMPTS_DIR.resolve()

        content = PromptLoader(resolved).load_system_prompt(
            "safety_classifier", PROMPT_VERSION
        )
        assert len(content) > 0


class TestResolvePromptsBaseDirWrongButSet:
    def test_live_env_relative_value_reanchors_from_ai_server_cwd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-021's actual live repro: `PROMPTS_BASE_DIR=docs/ai/prompts`
        (this repo's own `.env` value, REV-021-confirmed) does NOT resolve
        against cwd=`apps/ai-server` (the documented CLI invocation
        convention) — the fix must re-anchor it against PROJECT_ROOT and
        recover, not silently degrade every agent."""
        monkeypatch.setenv("PROMPTS_BASE_DIR", _LIVE_ENV_RELATIVE_VALUE)
        ai_server_dir = PROJECT_ROOT / "apps" / "ai-server"
        monkeypatch.chdir(ai_server_dir)

        # Precondition: the raw value really does NOT resolve from this cwd
        # (the exact silent-degrade trigger BUG-021 describes).
        assert not Path(_LIVE_ENV_RELATIVE_VALUE).is_dir()

        resolved = resolve_prompts_base_dir(PROJECT_ROOT)

        assert resolved == _REAL_PROMPTS_DIR.resolve()

        content = PromptLoader(resolved).load_system_prompt(
            "safety_classifier", PROMPT_VERSION
        )
        assert len(content) > 0

    def test_wrong_path_with_no_reanchor_recovery_fails_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Set-and-wrong, unrecoverable even re-anchored against
        PROJECT_ROOT -> RuntimeError (fail-fast), never a silent fallback."""
        monkeypatch.setenv(
            "PROMPTS_BASE_DIR", "this_directory_does_not_exist_anywhere_bug021"
        )

        with pytest.raises(RuntimeError, match="PROMPTS_BASE_DIR"):
            resolve_prompts_base_dir(PROJECT_ROOT)


class TestAgentPromptsDegradedFlag:
    """The other half of the BUG-021 fix: even once the base dir resolves,
    a missing *specific* prompt file must be machine-visible on the agent's
    own output artifact, not just a WARNING log line. Real `PromptLoader`
    throughout; only the LLM router/adapter are mocked (same pattern as
    `tests/test_safety_failclosed.py::_make_agent`/`_wire`)."""

    @staticmethod
    def _make_agent(prompt_loader: PromptLoader) -> SafetyClassifierAgent:
        agent = SafetyClassifierAgent.__new__(SafetyClassifierAgent)
        agent._router = MagicMock()
        agent._prompt_loader = prompt_loader
        agent._router.select_model.return_value = MagicMock(
            adapter_name="test",
            model_id="test",
            supports_json_schema=False,
            supports_json_object=False,
        )
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.chat_timed = AsyncMock(
            return_value=MagicMock(
                content='{"risk_level": "none", "categories": [], '
                '"flagged_phrases": [], "confidence": 0.9, '
                '"reason_summary": "benign"}',
                model="test-model",
                latency_ms=1.0,
            )
        )
        agent._router.get_adapter.return_value = adapter
        agent._router.record_success = MagicMock()
        agent._router.record_failure = MagicMock()
        agent._router.get_fallback.return_value = None
        return agent

    @pytest.mark.asyncio
    async def test_correct_path_real_prompt_loads_not_degraded(self) -> None:
        """Real PromptLoader pointed at the real prompts dir -> the real v2
        prompt loads -> prompts_degraded is False."""
        agent = self._make_agent(PromptLoader(_REAL_PROMPTS_DIR))

        out = await agent.run(
            SafetyInput(session_id="t-bug021-ok", user_message="괜찮아요", conversation_history=[])
        )

        assert out.prompts_degraded is False

    @pytest.mark.asyncio
    async def test_wrong_but_existing_dir_missing_prompt_sets_degraded_flag(
        self, tmp_path
    ) -> None:
        """Real PromptLoader pointed at a real, EXISTING directory that
        lacks `safety_classifier/v2.system.md` (the base dir resolved, but
        this agent's specific prompt file is still missing — the residual
        failure mode `resolve_prompts_base_dir`'s directory-existence check
        alone cannot catch) -> load_system_prompt raises FileNotFoundError,
        the agent's own catch site falls back to the generic prompt, and
        prompts_degraded is now True and machine-visible on the artifact —
        not just a WARNING log line (BUG-021 proposed fix (b))."""
        agent = self._make_agent(PromptLoader(tmp_path))

        out = await agent.run(
            SafetyInput(
                session_id="t-bug021-degraded", user_message="괜찮아요", conversation_history=[]
            )
        )

        assert out.prompts_degraded is True
        # Sanity: the run still completed — degrade, don't crash.
        assert out.model_used == "test-model"
