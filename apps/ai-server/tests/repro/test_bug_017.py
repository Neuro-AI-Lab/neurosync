"""BUG-017 repro/documentation: VP-003 RAG-mode LLM-output-reliability
failure (REV-010 finding 2, `discussion.md`; EXP-005 RAG arm, first
activation, 2026-07-08). Both of VP-003's 2 RAG runs failed to produce a
parseable domain_inference LLM response, before the risk-lexicon cascade
ever ran (`filter_summary.candidates_before=0` both runs -- confirmed
directly from `experiments/EXP-005/runs/rag/VP-003/run{1,2}/*_domain_
inference.json`, gitignored, read but not depended on at test runtime):

  run1 (`experiments/EXP-005/runs/rag/VP-003/run1/stdout.log`, verbatim):
    "src.agents.domain_inference WARNING DomainInference parse failure:
     LLM response JSON parse failure: Unterminated string starting at:
     line 157 column 20 (char 5053)"
  run2 (`experiments/EXP-005/runs/rag/VP-003/run2/stdout.log`, verbatim):
    "src.agents.domain_inference WARNING DomainInference parse failure:
     LLM response schema validation failure: 6 error(s)"

Both preceded by a successful Stage 1 (`f2.stage1.ok -- mode=rag,
chunks=11` / `chunks=6` -- confirmed in the same stdout.log files) -- the
failure is Stage 2 (LLM output) only. `DomainInferenceAgent.run`'s
fail-safe path (`_parse` returning `(None, reason)` ->
`DomainInferenceOutput` with empty candidates, `src/agents/domain_
inference.py:226-237`, confirmed by direct code read) handled both
cleanly: no crash, `mode` still honestly reported as `rag`. This is NOT
itself a defect -- the fail-safe behavior is already covered generically
by `tests/test_domain_inference.py::TestAgentRuntime::
test_run_degrades_gracefully_on_json_parse_failure` / `..._on_schema_
validation_failure`.

The evaluability-blocking defect (this BUG) is that VP-003 -- this
project's own governing chain's (VAL-006/REV-008/DATASET-004) highest-
scrutiny persona -- has now failed 100% (2/2) of its RAG-mode attempts,
and no live LLM call is available to this qa agent to re-run VP-003 RAG
and observe a clean pass/fail (REV-010's own resolution #1, "re-run VP-003
RAG n=2 cleanly", is a developer/experiment-tracker follow-up with live
LLM access -- out of this repro's reach and qa's charter, which permits
no src/ changes and no live LLM calls here).

This file adds two things beyond REV-010's original finding, both
verifiable without a live LLM call:

  1. `TestBug017MaxTokensConfig` -- confirms REV-010's cited config value
     directly through the code path (not just a source-line read):
     `DomainInferenceAgent._call` (`domain_inference.py:128-143`)
     hardcodes `max_tokens=1536` on every `chat_timed()` call, RAG or
     llm_only alike -- no per-mode budget, no config override, so the
     same 1536-token ceiling applies to VP-003's heavier RAG-mode prompt
     (11 retrieved chunks, `f2.stage1.ok -- chunks=11`) as to a bare
     llm_only call with zero chunks.
  2. `TestBug017TruncatedJsonReproShape` -- reproduces the SHAPE of the
     real run1 failure (a JSON response cut off mid-string-literal, not
     `test_run_degrades_gracefully_on_json_parse_failure`'s simpler
     `"not json at all"` fixture) through the real `_parse`/`run` code
     path, confirming the fail-safe handles this exact failure shape too.
  3. `TestBug017FinishReasonDiscarded` -- a code-level gap qa found while
     verifying the max_tokens=1536 truncation hypothesis:
     `DomainInferenceAgent._call` discards `resp.finish_reason` and
     `resp.usage` from the adapter's `ChatResponse` (`src/adapters/
     base.py:20-27`; populated by `SolarPro3Adapter`, `src/adapters/
     solar_pro3.py:113` `finish_reason=choice.finish_reason` and the
     `usage` dict two lines above) -- `finish_reason == "length"` is the
     OpenAI-compatible API's own direct signal that a completion was cut
     off by the token budget, and it is silently dropped before it ever
     reaches `DomainInferenceOutput` (`src/schemas/domain_inference.py:
     125-132`, no such field) or a log line. **This means REV-010's
     truncation hypothesis is currently unfalsifiable from this
     pipeline's own artifacts** -- not on the 2 failed runs (no
     ChatResponse was ever parsed into anything logged), and not on any
     future re-run either, until this gap is closed. Recommend this be
     folded into BUG-017's fix scope or filed as a fast-follow: log/carry
     `finish_reason`+`usage` on every parse failure at minimum.

     BUG-017 PHASE A (2026-07-08, PLAN-2026-W28-G T1-dev): this gap is now
     closed -- `_call`/`run` (`domain_inference.py`) capture and log
     `finish_reason`/`usage` on EVERY call outcome (success and parse/schema
     failure alike) and `DomainInferenceOutput` now carries both fields.
     `TestBug017FinishReasonDiscarded` below is inverted accordingly (was:
     demonstrates the gap; now: demonstrates the gap is closed). Raising
     `max_tokens` itself is still BUG-017 phase B, deferred pending a live
     diagnostic run -- explicitly NOT part of this fix.

Order-of-magnitude plausibility note on char 5053 (documented here, not
asserted by an automated test -- no solar-pro3 tokenizer is available in
this environment to compute this precisely, and see finding 3 above for
why the actual usage.completion_tokens figure is unrecoverable from this
project's own logs for the real failed runs): 1536 completion tokens at a
typical ~2-4 chars/token ratio for mixed Korean-hangul + JSON-structural
content spans roughly 3000-6100 characters, which brackets char 5053 --
consistent with, but not proof of, the truncation hypothesis. This matches
REV-010's own "correlation, not established causation" framing and should
not be upgraded to a confirmed-cause claim without instrumenting
finish_reason/usage capture and observing an actual `finish_reason ==
"length"` on a re-run.

BUG-017 PHASE B (2026-07-09, PLAN-2026-W28-G T1-dev-B): the diagnostic run
(`docs/ai/simulation_results/VP-003/VP-003_20260709_110457_domain_
inference.json`, `feat/f2-rag-remediation`, phase A instrumentation live)
CONFIRMED the truncation hypothesis directly, no longer by inference --
`finish_reason="length"` and `usage={"prompt_tokens": 2665,
"completion_tokens": 1536, "total_tokens": 4201}`: `completion_tokens`
exactly equals the old `max_tokens` ceiling, i.e. the completion was cut
off at the budget, not stopped naturally. `_call`'s `max_tokens` is raised
from 1536 to 4096 (global -- both `llm_only`/`rag` -- see this fix's own
`_call` docstring for the value/scope rationale; `llm_only` is unaffected
in practice since its shorter outputs already finish with
`finish_reason="stop"` well under the old ceiling). `TestBug017MaxTokens
Config` below is updated to assert the new value (single-variable change,
REV-011 binding -- no retrieval/prompt-size change bundled with this fix).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from tests.test_domain_inference import _base_input, _make_agent

# ── Test 1: max_tokens config value -- BUG-017 phase B raised value ──


class TestBug017MaxTokensConfig:
    @pytest.mark.asyncio
    async def test_call_passes_max_tokens_4096(self) -> None:
        """Confirms the exact config value through the live code path (not
        just a grep of domain_inference.py): every chat_timed() call this
        agent makes, RAG or llm_only, is capped at 4096 completion tokens
        -- BUG-017 phase B's global raise from the old 1536 ceiling that
        the live diagnostic run confirmed was truncating VP-003 RAG-mode
        output (`finish_reason="length"`, `usage.completion_tokens==1536`,
        exactly the old ceiling). Still no per-mode budget split (a global
        raise was chosen; see this fix's `_call` docstring for why)."""
        agent = _make_agent()
        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        resp = MagicMock()
        resp.content = '{"domain_candidates": [], "department_candidates": [], "summary": ""}'
        resp.model = "test-model"
        resp.latency_ms = 1.0
        resp.finish_reason = None
        resp.usage = None
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.chat_timed = AsyncMock(return_value=resp)
        agent._router.get_adapter.return_value = adapter
        agent._router.record_success = MagicMock()
        agent._router.record_failure = MagicMock()

        await agent.run(_base_input(retrieval_mode="rag"))

        adapter.chat_timed.assert_awaited_once()
        _, kwargs = adapter.chat_timed.call_args
        assert kwargs["max_tokens"] == 4096, (
            "BUG-017 phase B: max_tokens config drifted from the raised "
            "value (domain_inference.py, DomainInferenceAgent._call) -- "
            "update error.md/REV-011 cross-reference."
        )


# ── Test 2: reproduce the real run1 failure SHAPE (unterminated string) ──

# Mirrors the real run1 payload's structure (domain_candidates -> evidence
# -> quote) cut off mid-string-literal -- NOT a generic "not json at all"
# blob. Verified locally to raise json.JSONDecodeError("Unterminated
# string starting at: ...") exactly like the real stdout.log line.
_TRUNCATED_JSON_LIKE_RUN1 = (
    '{"domain_candidates": [{"domain": "depression", "confidence": 0.7, '
    '"evidence": [{"source_type": "rag_chunk", "source_id": "case_card:940", '
    '"quote": "내담자는 잠들기 어렵거나 자주 깨는 등의 수면 문제를 겪고 있으며'
    # (cut off mid-string -- no closing quote/brace, matching "Unterminated
    # string" rather than a delimiter/EOF error)
)

# Mirrors the real run2 failure's SHAPE: syntactically VALID json, but
# multiple schema violations (domain not in the allowed enum, confidence
# out of [0,1] range, empty evidence lists violating min_length=1, empty
# department string) -- exercises DomainInferenceLLMResponse.model_
# validate's multi-error path the same way the real "schema validation
# failure: 6 error(s)" line did. This fixture independently verified to
# raise error_count()==7 (not claimed to be bit-for-bit identical to the
# real run2 payload, which was never persisted -- only its error COUNT
# and MESSAGE SHAPE are on record in stdout.log); the test below asserts
# on the generic "validation failure ... error(s)" shape, not an exact
# count, since the real payload is not recoverable for an exact replay.
_SCHEMA_INVALID_JSON_LIKE_RUN2 = (
    '{"domain_candidates": ['
    '{"domain": "not_a_real_domain", "confidence": 1.7, "evidence": []},'
    '{"domain": "depression", "confidence": -0.2, "evidence": []}'
    '], "department_candidates": [{"department": "", "reason": ""}]}'
)


class TestBug017TruncatedJsonReproShape:
    @pytest.mark.asyncio
    async def test_unterminated_string_json_degrades_gracefully(self) -> None:
        """Reproduces the SHAPE of the real run1 failure and confirms the
        fail-safe path: empty candidates, no crash, an honest
        reason_summary carrying the actual JSONDecodeError text, and the
        `rag` mode label preserved even though the call failed."""
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire_content(agent, _TRUNCATED_JSON_LIKE_RUN1)

        out = await agent.run(_base_input(retrieval_mode="rag"))

        assert out.domain_candidates == []
        assert out.department_candidates == []
        assert "parse failure" in out.reason_summary.lower()
        assert "unterminated string" in out.reason_summary.lower(), (
            f"expected the real run1 failure shape (unterminated string), "
            f"got reason_summary={out.reason_summary!r}"
        )
        assert out.retrieval_meta.mode == "rag"

    @pytest.mark.asyncio
    async def test_schema_invalid_json_degrades_gracefully(self) -> None:
        """Reproduces the SHAPE of the real run2 failure (valid JSON,
        invalid schema, multiple errors) and confirms the same fail-safe
        path."""
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire_content(agent, _SCHEMA_INVALID_JSON_LIKE_RUN2)

        out = await agent.run(_base_input(retrieval_mode="rag"))

        assert out.domain_candidates == []
        assert out.department_candidates == []
        assert "validation failure" in out.reason_summary.lower()
        assert "error(s)" in out.reason_summary.lower()
        assert out.retrieval_meta.mode == "rag"


def _wire_content(agent, content: str) -> AsyncMock:
    """Local re-implementation of tests.test_domain_inference._wire (that
    helper is module-private; duplicated here rather than imported to keep
    this repro self-contained if the shared harness changes shape)."""
    agent._router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    resp = MagicMock()
    resp.content = content
    resp.model = "test-model"
    resp.latency_ms = 1.0
    # BUG-017 phase A: explicit, matching a real ChatResponse's defaults --
    # see tests.test_domain_inference._wire's own comment.
    resp.finish_reason = None
    resp.usage = None
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    agent._router.get_adapter.return_value = adapter
    agent._router.record_success = MagicMock()
    agent._router.record_failure = MagicMock()
    return adapter


# ── Test 3: finish_reason/usage silently discarded -- the diagnostic gap ─


class TestBug017FinishReasonDiscarded:
    @pytest.mark.asyncio
    async def test_finish_reason_and_usage_now_captured_and_persisted(self) -> None:
        """BUG-017 phase A (2026-07-08, this dispatch): the diagnostic gap
        qa found beyond REV-010's original scope is closed. When the
        adapter's response carries `finish_reason="length"` (the OpenAI-
        compatible API's direct signal that the completion was cut off by
        max_tokens) and `usage.completion_tokens == 1536` (the budget
        fully consumed), DomainInferenceAgent now threads both through
        `_call` -> `run` into `DomainInferenceOutput.finish_reason`/`.usage`
        -- so a future RAG-mode truncation hypothesis is falsifiable
        directly from the agent's own output, not just inferred from a
        character offset. (Raising max_tokens itself is BUG-017 phase B,
        deferred pending a live diagnostic run -- NOT part of this fix.)"""
        agent = _make_agent()
        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        resp = MagicMock()
        resp.content = '{"domain_candidates": [], "department_candidates": [], "summary": ""}'
        resp.model = "test-model"
        resp.latency_ms = 1.0
        resp.finish_reason = "length"  # the real truncation signal
        resp.usage = {"prompt_tokens": 900, "completion_tokens": 1536, "total_tokens": 2436}
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.chat_timed = AsyncMock(return_value=resp)
        agent._router.get_adapter.return_value = adapter
        agent._router.record_success = MagicMock()
        agent._router.record_failure = MagicMock()

        out = await agent.run(_base_input(retrieval_mode="rag"))

        # The signal was right there on the response object --
        assert resp.finish_reason == "length"
        assert resp.usage["completion_tokens"] == 1536
        # -- and now it DOES reach the agent's output.
        assert out.finish_reason == "length", (
            "BUG-017 phase A regression: DomainInferenceOutput.finish_reason "
            "no longer carries the adapter's finish_reason."
        )
        assert out.usage == {"prompt_tokens": 900, "completion_tokens": 1536, "total_tokens": 2436}
        out_dict = out.model_dump()
        assert out_dict["finish_reason"] == "length"
        assert out_dict["usage"]["completion_tokens"] == 1536
