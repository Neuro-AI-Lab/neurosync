"""BUG-019 repro/documentation: schema-validation-failure raw-response
diagnostic gap (RAG arm, EXP-006 certification batch, 2026-07-09).

BUG-017 phase B (`max_tokens` 1536->4096) resolved the diagnosed truncation
failure mode -- confirmed live, all 3 of this batch's RAG-arm LLM-output
failures show `finish_reason="stop"` (not `"length"`), with
`completion_tokens` far below the new 4096 ceiling (727/854/1590 -- see
`experiments/EXP-006/runs/rag/VP-003/run{1,2}/*_domain_inference.json` and
`.../rag/VP-001/run1/*_domain_inference.json`, independently re-read by qa,
not accepted from result.md's prose alone). But VP-003 RAG is still 0/2
interpretable this batch, and a previously-clean persona (VP-001/run1)
newly failed the same way -- via a DISTINCT failure mode: syntactically
valid JSON that fails Pydantic schema validation (`ValidationError`), not a
truncated/malformed JSON parse failure. This is BUG-017's residual, not a
reopening of it (BUG-017's own diagnosed mechanism -- truncation -- does
not recur anywhere in this batch; see `TestBug019FinishReasonProvesNotBug017`
below).

Verbatim log lines (independently re-read by qa from the artifacts, not
copied from result.md):

  experiments/EXP-006/runs/rag/VP-003/run1/stdout.log:
    "src.agents.domain_inference WARNING DomainInference parse failure:
     LLM response schema validation failure: 1 error(s) (model=
     solar-pro3-260323, finish_reason=stop, usage={'prompt_tokens': 2665,
     'completion_tokens': 727, 'total_tokens': 3392})"
  experiments/EXP-006/runs/rag/VP-003/run2/stdout.log:
    "... schema validation failure: 3 error(s) ... finish_reason=stop,
     usage={'prompt_tokens': 2273, 'completion_tokens': 854, ...}"
  experiments/EXP-006/runs/rag/VP-001/run1/stdout.log (new this batch):
    "... schema validation failure: 3 error(s) ... finish_reason=stop,
     usage={'prompt_tokens': 3582, 'completion_tokens': 1590, ...}"

The root cause of *why* the LLM's syntactically-valid JSON fails schema
validation is NOT diagnosable from this pipeline's own artifacts, and this
file's tests exist to demonstrate exactly that gap, deterministically,
without a live LLM call:

  `DomainInferenceAgent._parse` (`src/agents/domain_inference.py:124-134`)
  calls `DomainInferenceLLMResponse.model_validate(data)` inside a
  try/except `ValidationError`, and on failure returns only
  `f"... schema validation failure: {exc.error_count()} error(s)"` -- an
  integer count, never `exc.errors()` (the field-level detail: which
  field(s), what type/value, what constraint was violated) and never the
  raw `content` string that was parsed as `data` in the first place.
  `DomainInferenceAgent.run` (`:264-277`) threads `reason` (the count-only
  string) into `DomainInferenceOutput.reason_summary` but has no code path
  that captures or persists the raw LLM response text anywhere -- not in
  the returned `DomainInferenceOutput` object (`src/schemas/domain_
  inference.py` has no such field, confirmed by direct read: the only
  BUG-017-phase-A additions are `finish_reason`/`usage`, both scalars/dicts,
  neither the response body), not in a log line (only `reason`, `model_used`,
  `finish_reason`, `usage` are logged, per the same `run()` read), and not
  in `apps/ai-server/src/f2.py`'s artifact/report builders (`_repro_
  metadata`/`_build_artifact`, confirmed by direct read -- both only
  forward `finish_reason`/`usage`, never a raw-content field).

Confirmed independently against the 3 real EXP-006 artifacts (not just
this file's synthetic fixtures): `python -c "import json; d=json.load(open(
'experiments/EXP-006/runs/rag/VP-003/run1/VP-003_20260709_112154_domain_
inference.json')); print(sorted(d.keys()))"` -> no `raw_content`/`raw_
response`/`llm_response` key anywhere in the top-level artifact, `repro`
block, or elsewhere -- exactly as this file's tests predict for the
synthetic case.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.domain_inference import DomainInferenceAgent
from tests.test_domain_inference import _base_input, _make_agent

# Mirrors the real failures' SHAPE: syntactically valid JSON, schema
# violations only (domain not in the allowed enum + confidence out of
# [0,1] range) -- exercises the same ValidationError/error_count() path
# the 3 real EXP-006 failures hit. Not claimed to be bit-for-bit identical
# to any real payload (none of the 3 real payloads were persisted -- that
# is exactly this BUG's finding).
_SCHEMA_INVALID_CONTENT = (
    '{"domain_candidates": ['
    '{"domain": "not_a_real_domain", "confidence": 1.7, "evidence": []},'
    '{"domain": "depression", "confidence": -0.2, "evidence": []}'
    '], "department_candidates": [], "summary": "some model summary text"}'
)


def _wire_schema_invalid(agent: DomainInferenceAgent, *, finish_reason: str = "stop") -> AsyncMock:
    agent._router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    resp = MagicMock()
    resp.content = _SCHEMA_INVALID_CONTENT
    resp.model = "test-model"
    resp.latency_ms = 1.0
    resp.finish_reason = finish_reason
    resp.usage = {"prompt_tokens": 900, "completion_tokens": 300, "total_tokens": 1200}
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    agent._router.get_adapter.return_value = adapter
    agent._router.record_success = MagicMock()
    agent._router.record_failure = MagicMock()
    return adapter


class TestBug019FinishReasonProvesNotBug017:
    @pytest.mark.asyncio
    async def test_schema_failure_with_finish_reason_stop_is_distinct_from_bug017_truncation(
        self,
    ) -> None:
        """BUG-017 phase A's own instrumentation is what LETS us tell the two
        failure modes apart: `finish_reason="stop"` (natural completion) on
        a schema-validation failure proves this is NOT the BUG-017
        truncation mechanism (which would show `finish_reason="length"`) --
        exactly the distinction the real VP-003/VP-001 EXP-006 runs show."""
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire_schema_invalid(agent, finish_reason="stop")

        out = await agent.run(_base_input(retrieval_mode="rag"))

        assert out.domain_candidates == []
        assert "validation failure" in out.reason_summary.lower()
        assert out.finish_reason == "stop", (
            "expected the BUG-019 failure signature (natural completion, "
            "schema-invalid content) -- finish_reason='length' would be "
            "BUG-017's truncation mechanism, not this one"
        )


class TestBug019RawResponseNotPersistedAnywhere:
    """The core diagnostic-gap demonstration: on a schema-validation
    failure, the raw LLM response text -- the one artifact that would let a
    human or a future automated diagnosis see WHICH field(s) failed and
    WHY -- is discarded at `_parse` and never threaded anywhere by `run`."""

    @pytest.mark.asyncio
    async def test_output_object_carries_no_raw_content_field(self) -> None:
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire_schema_invalid(agent)

        out = await agent.run(_base_input(retrieval_mode="rag"))

        # finish_reason/usage ARE captured (BUG-017 phase A, already fixed) --
        assert out.finish_reason == "stop"
        assert out.usage == {"prompt_tokens": 900, "completion_tokens": 300, "total_tokens": 1200}
        # -- but nothing on the output object carries the raw response text,
        # nor any field-level validation detail (which field failed, what
        # value/constraint) beyond the bare integer count embedded in the
        # reason string.
        out_dict = out.model_dump()
        assert not any(
            "raw" in k.lower() or "content" in k.lower() or "response" in k.lower()
            for k in out_dict
        ), (
            f"BUG-019: expected no raw-response-carrying field on "
            f"DomainInferenceOutput; found keys={sorted(out_dict.keys())}. "
            f"If this now fails, BUG-019's diagnostic gap has been closed -- "
            f"invert this assertion per the BUG-007 convention and mark "
            f"BUG-019 resolved."
        )
        assert out.reason_summary == "LLM response schema validation failure: 5 error(s)", (
            "the reason string carries only an integer error count -- no "
            "field name, no offending value, no constraint description"
        )

    @pytest.mark.asyncio
    async def test_parse_return_value_discards_content_on_validation_error(self) -> None:
        """Direct unit check on `_parse` itself (no LLM call): confirms the
        static method's own return contract discards `content` on a
        `ValidationError` -- the exact point BUG-019's gap originates."""
        import json

        from pydantic import ValidationError

        parsed, reason = DomainInferenceAgent._parse(_SCHEMA_INVALID_CONTENT)

        assert parsed is None
        assert reason == "LLM response schema validation failure: 5 error(s)"
        # The reason string is derived from exc.error_count() only -- confirm
        # the richer exc.errors() detail (and the original `content`/`data`)
        # is available at this exact point but is NOT what `_parse` returns,
        # i.e. it is available-but-discarded, not unavailable-in-principle.
        data = json.loads(_SCHEMA_INVALID_CONTENT)
        try:
            from src.schemas.domain_inference import DomainInferenceLLMResponse

            DomainInferenceLLMResponse.model_validate(data)
            pytest.fail("fixture should not validate -- update _SCHEMA_INVALID_CONTENT")
        except ValidationError as exc:
            assert exc.error_count() == 5
            assert len(exc.errors()) == 5, (
                "field-level detail (exc.errors()) exists at the exact "
                "point _parse() discards it down to a bare integer count"
            )


class TestBug019JsonParseFailurePathAlsoDiscardsContent:
    """Companion check: the sibling JSON-parse-failure branch of `_parse`
    (used by BUG-017's original run1-shape failure, distinct from this
    BUG's schema-validation-failure shape) has the identical discard
    property -- confirming this is a `_parse`-wide gap, not specific to
    the `ValidationError` branch alone."""

    @pytest.mark.asyncio
    async def test_json_decode_failure_also_has_no_raw_content_persisted(self) -> None:
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        resp = MagicMock()
        resp.content = '{"domain_candidates": [{"domain": "depression"'  # truncated, unparseable
        resp.model = "test-model"
        resp.latency_ms = 1.0
        resp.finish_reason = "length"
        resp.usage = {"prompt_tokens": 900, "completion_tokens": 1536, "total_tokens": 2436}
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.chat_timed = AsyncMock(return_value=resp)
        agent._router.get_adapter.return_value = adapter
        agent._router.record_success = MagicMock()
        agent._router.record_failure = MagicMock()

        out = await agent.run(_base_input(retrieval_mode="rag"))

        out_dict = out.model_dump()
        assert not any(
            "raw" in k.lower() or "content" in k.lower() or "response" in k.lower()
            for k in out_dict
        )
        assert "parse failure" in out.reason_summary.lower()
