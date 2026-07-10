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

BUG-019 INSTRUMENTATION (2026-07-09, PLAN-2026-W28-H Wave 3, developer):
the diagnostic gap this file originally demonstrated is now closed.
`DomainInferenceAgent._parse` (`domain_inference.py`) returns a third tuple
element, `validation_errors` (`exc.errors()`'s field-level detail -- which
field, what value, what constraint -- as a list of plain dicts, `None` on a
JSON-parse failure or success), and `run()` now threads BOTH that and the
raw LLM response text (`raw_content`, already in scope from the `_call()`
result) into `DomainInferenceOutput.validation_errors`/`.raw_response` on
every failure branch (JSON-parse and schema-validation alike, mirroring
BUG-017 phase A's finish_reason/usage capture-on-every-failure-outcome
precedent). `f2.py`'s `_repro_metadata`/`_build_artifact`/`_build_report`
mirror both fields into the saved artifact JSON and the report's new "LLM
failure diagnostics (BUG-019)" section, same as `finish_reason`/`usage`
already do. Per this project's established repro-test convention
(BUG-007/009/014/015/016/017 precedent), the tests below that originally
demonstrated the gap are now inverted to assert the fix: the raw response
text and the field-level `errors()` detail ARE now persisted. This does not
by itself diagnose the 3 real EXP-006 failures' root cause (no live LLM
re-run was performed by this instrumentation change) or re-run VP-003 RAG
n=2 cleanly -- both remain open, tracked by BUG-019 itself pending the next
diagnostic dispatch (PLAN-2026-W28-H, ADR-016's certification path).

BUG-019 ROOT-CAUSE FIX (2026-07-09, developer, using EXP-007's live
diagnostic capture): EXP-007 (`result.md`) reproduced the failure live
(VP-003/run1: 1 error; VP-001/run2: 6 errors, both `finish_reason="stop"`)
and captured the field-level `validation_errors` — every offending value is
a `literal_error` on `evidence[].source_type` with `input` one of `"qa"`,
`"qa:1502"`, `"qa:1537"`, `"qa:532"` — all `rag.qa`-table-sourced.
Root cause: `RetrievedChunk.source_type` (DB table origin: `"case_card"`/
`"qa"`, `schemas/domain_inference.py:81`) and `DomainEvidence.source_type`
(output enum `Literal["rag_chunk", "utterance"]`, `:35`) share a field NAME
across different value DOMAINS; the prompt's per-chunk listing used to print
the table-origin value in the exact visual slot the output field occupies
(`domain_inference.py:83-85`, pre-fix), so the model intermittently echoed
it. The fix, mirroring BUG-016's `_normalize_rag_chunk_source_id`
precedent: (a) the per-chunk prompt listing is reworded so the table-origin
label no longer sits in that slot (defense in depth, not deterministic
alone — same status as BUG-016's prompt-wording half); (b) `_parse`
(`domain_inference.py`) calls `_normalize_source_type_collision` on the
raw parsed dict, BEFORE `DomainInferenceLLMResponse.model_validate`, to
narrowly coerce a `source_type` value matching the known collision shape
(`"case_card"`/`"qa"`, optionally `:<digits>`-suffixed) to `"rag_chunk"`.
This coercion lives in `domain_inference.py`, not `src.eval.f2_grounding`
(where BUG-016's `source_id` fix lives), because `source_type` is
Pydantic-`Literal`-constrained: by the time `f2_grounding.check_evidence`
ever sees a `source_type` value, Pydantic has already either accepted it or
raised `ValidationError` — there is no post-parse hook that can retroactively
fix an already-raised validation error. The classes below (originally named
for the diagnostic-gap this file demonstrated) are unaffected by this fix —
their fixture (`_SCHEMA_INVALID_CONTENT`) exercises unrelated violations
(invalid `domain` enum value + out-of-range `confidence`), not the
`source_type` collision, and continue to fail validation exactly as before
(confirming the fix is narrow, not a blanket validation bypass). The new
`TestBug019SourceTypeCollisionFix` class below uses EXP-007's own captured
failing patterns as fixtures.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.domain_inference import (
    DomainInferenceAgent,
    _normalize_source_type_collision,
)
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
    """BUG-019 fix (2026-07-09): on a schema-validation failure, the raw LLM
    response text and the field-level `ValidationError.errors()` detail --
    the two artifacts that let a human or a future automated diagnosis see
    WHICH field(s) failed and WHY -- ARE now captured at `_parse` and
    threaded through by `run`. This class originally demonstrated the
    opposite (both discarded); assertions inverted per the BUG-007
    convention, class name kept for continuity with `error.md` BUG-019's
    own cross-reference."""

    @pytest.mark.asyncio
    async def test_output_object_now_carries_raw_response_and_validation_errors(self) -> None:
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire_schema_invalid(agent)

        out = await agent.run(_base_input(retrieval_mode="rag"))

        # finish_reason/usage remain captured (BUG-017 phase A, unaffected) --
        assert out.finish_reason == "stop"
        assert out.usage == {"prompt_tokens": 900, "completion_tokens": 300, "total_tokens": 1200}
        # -- and now the raw response text IS persisted, verbatim --
        assert out.raw_response == _SCHEMA_INVALID_CONTENT
        # -- and the field-level validation detail IS persisted too: 5
        # entries, matching exc.errors()'s own count for this fixture.
        assert out.validation_errors is not None
        assert len(out.validation_errors) == 5
        assert all(
            {"type", "loc", "msg"} <= set(e.keys()) for e in out.validation_errors
        ), "each entry should carry Pydantic's own error-detail keys"
        # reason_summary keeps its existing bare-count string for backward-
        # compatible log/console readability -- the field-level detail now
        # lives on validation_errors, this string is not being replaced.
        assert out.reason_summary == "LLM response schema validation failure: 5 error(s)"

    @pytest.mark.asyncio
    async def test_parse_return_value_now_returns_validation_errors(self) -> None:
        """Direct unit check on `_parse` itself (no LLM call): confirms the
        static method's own return contract now surfaces `exc.errors()` as
        its third tuple element on a `ValidationError` -- the exact point
        BUG-019's gap originated, now closed."""
        parsed, reason, validation_errors = DomainInferenceAgent._parse(_SCHEMA_INVALID_CONTENT)

        assert parsed is None
        assert reason == "LLM response schema validation failure: 5 error(s)"
        assert validation_errors is not None
        assert len(validation_errors) == 5
        assert all(isinstance(e, dict) for e in validation_errors)
        assert all({"type", "loc", "msg"} <= set(e.keys()) for e in validation_errors)


class TestBug019JsonParseFailurePathAlsoDiscardsContent:
    """Companion check: the sibling JSON-parse-failure branch of `_parse`
    (used by BUG-017's original run1-shape failure, distinct from this
    BUG's schema-validation-failure shape) now persists the raw response
    text too (symmetric fix, BUG-019) -- confirming the fix is a
    `_parse`-wide fix, not specific to the `ValidationError` branch alone.
    `validation_errors` stays `None` on this branch: no `ValidationError`
    was ever raised (the content never reached the schema-validation
    stage), so there is nothing for `exc.errors()` to have captured."""

    @pytest.mark.asyncio
    async def test_json_decode_failure_now_persists_raw_response(self) -> None:
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        resp = MagicMock()
        truncated_content = '{"domain_candidates": [{"domain": "depression"'  # unparseable
        resp.content = truncated_content
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

        assert out.raw_response == truncated_content
        assert out.validation_errors is None
        assert "parse failure" in out.reason_summary.lower()


# EXP-007's own captured field-level `validation_errors`, verbatim from
# `result.md` EXP-007 "#### Field-level `validation_errors` detail" sections
# — used here to build byte-shape-matching fixtures (not claimed to be the
# real full raw_response, which EXP-007 only quoted a bounded fragment of).
_VP003_RUN1_CONTENT = json.dumps({
    "domain_candidates": [
        {
            "domain": "sleep",
            "confidence": 0.5,
            "evidence": [
                {
                    # case_card-sourced evidence is correctly typed in the
                    # real EXP-007 data (0/24 anomalies, `result.md` EXP-007
                    # root-cause hypothesis item 2) — the model already
                    # emits the correct enum value here.
                    "source_type": "rag_chunk",
                    "source_id": "case_card:12",
                    "quote": "환자는 3개월간 불면을 호소함",
                },
                {
                    # EXP-007 VP-003/run1: offending input == "qa" (bare
                    # table name), source_id == "qa:745".
                    "source_type": "qa",
                    "source_id": "qa:745",
                    "quote": (
                        "35세 여성이 최근 3개월간 주 4일 이상 잠들기 어렵고, "
                        "한밤중에 자주 깨어나며"
                    ),
                },
            ],
        }
    ],
    "department_candidates": [],
    "summary": "sleep-related complaint with case_card + qa evidence",
})

_VP001_RUN2_CONTENT = json.dumps({
    "domain_candidates": [
        {
            "domain": "depression",
            "confidence": 0.6,
            "evidence": [
                {
                    # EXP-007 VP-001/run2: offending input == full source_id
                    # string "qa:1502" (model went further than the bare
                    # table name).
                    "source_type": "qa:1502",
                    "source_id": "qa:1502",
                    "quote": "주의력 저하는 우울증 등 여러 원인으로 발생할 수 있다",
                },
                {
                    "source_type": "qa:1537",
                    "source_id": "qa:1537",
                    "quote": "수면 부족이 지속되면 집중력 저하로 이어질 수 있다",
                },
            ],
        },
        {
            "domain": "anxiety",
            "confidence": 0.4,
            "evidence": [
                {
                    "source_type": "qa:532",
                    "source_id": "qa:532",
                    "quote": "과도한 스트레스가 불안 증상을 악화시킬 수 있다",
                },
            ],
        },
    ],
    "department_candidates": [],
    "summary": "depression/anxiety with qa-table evidence",
})


class TestBug019SourceTypeCollisionFix:
    """BUG-019 root-cause fix (2026-07-09): `RetrievedChunk.source_type`
    (DB table origin: "case_card"/"qa") and `DomainEvidence.source_type`
    (output enum) share a field name; the model intermittently echoes the
    table-origin value into the output field. `_parse` now narrowly coerces
    the known collision shape to "rag_chunk" BEFORE Pydantic validation.
    Fixtures above mirror EXP-007's own captured failing `validation_errors`
    patterns (`result.md` EXP-007), not synthetic guesses."""

    def test_normalize_coerces_bare_table_name(self) -> None:
        """EXP-007 VP-003/run1 shape: source_type=="qa" (bare)."""
        data = json.loads(_VP003_RUN1_CONTENT)
        normalized = _normalize_source_type_collision(data)

        evidence = normalized["domain_candidates"][0]["evidence"]
        assert evidence[0]["source_type"] == "rag_chunk", (
            "already-correctly-typed case_card-sourced evidence stays "
            "unchanged (idempotent no-op on an already-valid value)"
        )
        # The qa-table item is the one carrying the collision.
        assert evidence[1]["source_type"] == "rag_chunk"
        assert evidence[1]["source_id"] == "qa:745", "source_id is untouched, only source_type"

    def test_normalize_coerces_suffixed_source_id_copy(self) -> None:
        """EXP-007 VP-001/run2 shape: source_type=="qa:1502" (full source_id
        string copied into source_type, all 3 evidence items across 2
        candidates)."""
        data = json.loads(_VP001_RUN2_CONTENT)
        normalized = _normalize_source_type_collision(data)

        all_evidence = [
            e
            for c in normalized["domain_candidates"]
            for e in c["evidence"]
        ]
        assert len(all_evidence) == 3
        assert all(e["source_type"] == "rag_chunk" for e in all_evidence)
        # source_id values are untouched — only source_type was coerced.
        assert {e["source_id"] for e in all_evidence} == {"qa:1502", "qa:1537", "qa:532"}

    def test_normalize_also_covers_case_card_bare_and_suffixed(self) -> None:
        """Symmetric coverage per the root-cause hypothesis (EXP-007 did not
        observe a case_card offending value this batch, but the collision
        mechanism is table-agnostic — REV-011 single-variable discipline:
        this does not depend on which table)."""
        data = {
            "domain_candidates": [
                {
                    "domain": "trauma",
                    "confidence": 0.5,
                    "evidence": [
                        {"source_type": "case_card", "source_id": "case_card:9", "quote": "x"},
                        {"source_type": "case_card:9", "source_id": "case_card:9", "quote": "y"},
                    ],
                }
            ],
        }
        normalized = _normalize_source_type_collision(data)
        evidence = normalized["domain_candidates"][0]["evidence"]
        assert evidence[0]["source_type"] == "rag_chunk"
        assert evidence[1]["source_type"] == "rag_chunk"

    def test_normalize_leaves_already_valid_values_unchanged(self) -> None:
        """Idempotence / no-op on already-correct output — the common case."""
        data = {
            "domain_candidates": [
                {
                    "domain": "anxiety",
                    "confidence": 0.5,
                    "evidence": [
                        {"source_type": "rag_chunk", "source_id": "case_card:1", "quote": "x"},
                        {"source_type": "utterance", "source_id": "turn_2", "quote": "y"},
                    ],
                }
            ],
        }
        normalized = _normalize_source_type_collision(data)
        evidence = normalized["domain_candidates"][0]["evidence"]
        assert evidence[0]["source_type"] == "rag_chunk"
        assert evidence[1]["source_type"] == "utterance"

    def test_normalize_does_not_touch_genuinely_malformed_values(self) -> None:
        """The narrowness contract: a source_type value that does NOT match
        the known collision shape is left untouched — this coercion must not
        mask a genuinely malformed model output."""
        data = {
            "domain_candidates": [
                {
                    "domain": "anxiety",
                    "confidence": 0.5,
                    "evidence": [
                        {"source_type": "garbage", "source_id": "case_card:1", "quote": "x"},
                        # BUG-016-shaped collision (chunk_id= prefix) is a
                        # DIFFERENT defect class on a DIFFERENT field
                        # (source_id, not source_type here) — not this
                        # function's job, must stay untouched.
                        {"source_type": "chunk_id=qa:1", "source_id": "case_card:2", "quote": "y"},
                        # No colon separator — not the observed collision
                        # shape, must stay untouched.
                        {"source_type": "qa1502", "source_id": "case_card:3", "quote": "z"},
                    ],
                }
            ],
        }
        normalized = _normalize_source_type_collision(data)
        evidence = normalized["domain_candidates"][0]["evidence"]
        assert evidence[0]["source_type"] == "garbage"
        assert evidence[1]["source_type"] == "chunk_id=qa:1"
        assert evidence[2]["source_type"] == "qa1502"

    def test_parse_now_yields_valid_response_for_vp003_run1_shape(self) -> None:
        """End-to-end through `_parse` (not just the normalizer directly):
        EXP-007's VP-003/run1-shaped payload now parses successfully."""
        parsed, reason, validation_errors = DomainInferenceAgent._parse(_VP003_RUN1_CONTENT)

        assert parsed is not None, f"expected successful parse, got reason={reason!r}"
        assert reason == ""
        assert validation_errors is None
        assert len(parsed.domain_candidates) == 1
        evidence = parsed.domain_candidates[0].evidence
        assert evidence[0].source_type == "rag_chunk"
        assert evidence[1].source_type == "rag_chunk"
        assert evidence[1].source_id == "qa:745"

    def test_parse_now_yields_valid_response_for_vp001_run2_shape(self) -> None:
        """End-to-end through `_parse`: EXP-007's VP-001/run2-shaped payload
        (6 validation_errors pre-fix, all on evidence[].source_type) now
        parses successfully."""
        parsed, reason, validation_errors = DomainInferenceAgent._parse(_VP001_RUN2_CONTENT)

        assert parsed is not None, f"expected successful parse, got reason={reason!r}"
        assert reason == ""
        assert validation_errors is None
        assert len(parsed.domain_candidates) == 2
        all_evidence = [e for c in parsed.domain_candidates for e in c.evidence]
        assert len(all_evidence) == 3
        assert all(e.source_type == "rag_chunk" for e in all_evidence)

    @pytest.mark.asyncio
    async def test_agent_run_now_produces_candidates_for_vp001_run2_shape(self) -> None:
        """Full `agent.run()` path (mocked adapter): the fix means this no
        longer degrades to an empty output — matches the `success` branch,
        not the `parsed is None` degrade branch."""
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        resp = MagicMock()
        resp.content = _VP001_RUN2_CONTENT
        resp.model = "test-model"
        resp.latency_ms = 1.0
        resp.finish_reason = "stop"
        resp.usage = {"prompt_tokens": 3582, "completion_tokens": 1590, "total_tokens": 5172}
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.chat_timed = AsyncMock(return_value=resp)
        agent._router.get_adapter.return_value = adapter
        agent._router.record_success = MagicMock()
        agent._router.record_failure = MagicMock()

        out = await agent.run(_base_input(retrieval_mode="rag"))

        assert out.reason_summary == "domain/department candidates generated"
        assert len(out.domain_candidates) == 2
        assert out.raw_response is None, "raw_response is only populated on the failure branch"
        assert out.validation_errors is None

    def test_genuinely_malformed_source_type_still_fails_validation(self) -> None:
        """The narrowness contract, exercised through the real `_parse`
        entry point: a source_type value that is not the known collision
        shape (e.g. "garbage") still fails Pydantic validation honestly —
        the fix must not become a blanket bypass."""
        content = json.dumps({
            "domain_candidates": [
                {
                    "domain": "anxiety",
                    "confidence": 0.5,
                    "evidence": [
                        {"source_type": "garbage", "source_id": "case_card:1", "quote": "x"},
                    ],
                }
            ],
            "department_candidates": [],
            "summary": "",
        })

        parsed, reason, validation_errors = DomainInferenceAgent._parse(content)

        assert parsed is None
        assert "schema validation failure" in reason.lower()
        assert validation_errors is not None
        assert len(validation_errors) == 1
        assert validation_errors[0]["loc"] == ("domain_candidates", 0, "evidence", 0, "source_type")
        assert validation_errors[0]["input"] == "garbage"

    def test_unrelated_schema_violations_still_fail_validation(self) -> None:
        """Regression: the pre-existing `_SCHEMA_INVALID_CONTENT` fixture
        (invalid domain enum + out-of-range confidence, unrelated to
        source_type) is untouched by this fix — confirms the coercion did
        not become an accidental blanket validation bypass."""
        parsed, reason, validation_errors = DomainInferenceAgent._parse(_SCHEMA_INVALID_CONTENT)

        assert parsed is None
        assert reason == "LLM response schema validation failure: 5 error(s)"
        assert validation_errors is not None
        assert len(validation_errors) == 5
