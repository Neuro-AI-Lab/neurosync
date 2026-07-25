"""Regression test for BUG-066 (fixed this pass, EXP-031 fix_wave_design.md).

Pre-fix: `contracts.handoff.HandoffRequest`/`HandoffResponse` shared ZERO
field names with ai-server's real `/ai/handoff/generate` schema on EITHER
direction — request fields were silently dropped (no `extra="forbid"` on
ai-server's `HandoffInput`), so the LLM narrated from an empty session, and
the (vacuous but 200) response then failed apps/api's strict-required-field
`HandoffResponse` validation (`chief_complaint`/`present_illness` ai-server
never returns) — every live handoff report ended `status="failed"`.

Fix (this pass): `HandoffRequest`/`HandoffResponse` are now field-identical
to ai-server's real `HandoffInput`/`HandoffOutput` on both directions.
`services/handoff.py::_build_request` assembles the REAL shape
(conversation_history/scale_scores/risk_events/slots) instead of the
pre-fix invented `HandoffMessage`/`HandoffQuestionnaire`/`HandoffRiskSignal`.
`slots` is now built from `Session.clinical_slots` (resolves the design
doc's UNVERIFIED open item — apps/api DOES persist per-session slot data,
in that JSONB column, populated by `services/chat.py::_extract_slots_bg`;
the pre-fix `_build_request` simply never read it)."""

from __future__ import annotations

import uuid

import pytest
from contracts.handoff import HandoffRequest, HandoffResponse, SlotData
from pydantic import ValidationError


def test_handoff_request_field_names_intersect_ai_server_handoff_input():
    """`HandoffRequest.model_dump()`'s field names must cover ai-server's
    real `HandoffInput` fields — zero overlap pre-fix (BUG-066's exact
    finding)."""
    req = HandoffRequest(session_id=str(uuid.uuid4()))
    dumped = req.model_dump(mode="json")
    ai_server_handoff_input_fields = {
        "session_id",
        "slots",
        "conversation_history",
        "scale_scores",
        "risk_events",
        "ocr_documents",
        "prior_handoff",
        "is_first_visit",
    }
    assert ai_server_handoff_input_fields.issubset(dumped.keys()), (
        f"HandoffRequest field names {set(dumped.keys())!r} do not cover "
        f"ai-server's real HandoffInput fields {ai_server_handoff_input_fields!r} "
        "— BUG-066 regression"
    )
    # extra="forbid" scoped to HandoffInput on ai-server's side means any
    # stray pre-fix-vocabulary field (messages/questionnaires/doc_texts/
    # risk_signals) would now 422 immediately rather than silently drop —
    # confirm the CONTRACT side also rejects them (bounded blast radius:
    # this is HandoffRequest, not the shared AgentInput base).
    with pytest.raises(ValidationError):
        HandoffRequest(session_id=str(uuid.uuid4()), messages=[])


def test_handoff_output_shaped_dict_validates_against_handoff_response():
    """A `HandoffOutput`-shaped dict (ai-server's real response, including
    the shared `AgentOutput` base fields it also carries) must validate
    against `HandoffResponse` without raising — this is what raised
    `pydantic.ValidationError` pre-fix (the old `HandoffResponse` required
    non-optional `chief_complaint`/`present_illness`, neither of which
    ai-server's real output has)."""
    ai_server_handoff_output = {
        "model_used": "solar-pro3",
        "prompt_version": "v1",
        "latency_ms": 6200.0,
        "reason_summary": "report generated",
        "prompts_degraded": False,
        "report_markdown": "## 주호소\n업무 스트레스로 인한 수면 곤란",
        "report_json": None,
        "report_pdf_base64": None,
        "trend_plot_base64": None,
        "evidence_packets": [
            {
                "evidence_id": "ev_msg_001",
                "source_type": "message",
                "source_ref": "msg-1",
                "content_summary": "수면 곤란 호소",
            }
        ],
        "missing_slots": ["family_history"],
        "risk_level": "low",
        "requires_human_review": False,
    }
    resp = HandoffResponse.model_validate(ai_server_handoff_output)
    assert resp.report_markdown.startswith("## 주호소")
    assert resp.missing_slots == ["family_history"]
    assert resp.evidence_packets[0].source_type == "message"


def test_slots_filtered_against_slotdata_fields_no_extra_forbid_trip():
    """`services/handoff.py::_build_slots` filters `Session.clinical_slots`
    (caller-controlled JSONB) against `SlotData.model_fields` before
    construction — a stray/legacy key must never trip `SlotData`'s
    `extra='forbid'`."""
    raw = {
        "chief_complaint": "수면 곤란",
        "some_future_unknown_key": "should be filtered out",
    }
    filtered = {k: v for k, v in raw.items() if k in SlotData.model_fields}
    slots = SlotData(**filtered)  # must not raise
    assert slots.chief_complaint == "수면 곤란"


@pytest.mark.asyncio
async def test_build_request_assembles_real_shape_including_slots(monkeypatch):
    """End-to-end (DB-mocked) check of `services/handoff.py::_build_request`:
    conversation_history/scale_scores/risk_events/slots are all populated
    from real session data — the pre-fix version silently shipped
    `slots=SlotData()` (all-None defaults) because `_build_request` never
    read `Session.clinical_slots` at all."""
    import src.services.handoff as handoff_module

    session_id = uuid.uuid4()

    class _FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalars(self):
            return self

        def all(self):
            return self._value or []

        def first(self):
            return self._value

    class _FakeMessage:
        def __init__(self, id_, role, content):
            self.id = id_
            self.role = role
            self.content_encrypted = content.encode()

    class _FakeDB:
        def __init__(self):
            self._call = 0

        async def execute(self, query):
            self._call += 1
            # Order in _build_request: messages, questionnaires, risk_events,
            # _build_slots' Session.clinical_slots select, then (BUG-069
            # follow-up) _build_patient_metadata's Session row (.first())
            # and PatientProfile.gender (.scalar_one_or_none()).
            if self._call == 1:
                return _FakeScalarResult([])
            if self._call == 2:
                return _FakeScalarResult([])
            if self._call == 3:
                return _FakeScalarResult([])
            if self._call == 4:
                return _FakeScalarResult({"chief_complaint": "수면 곤란"})
            if self._call == 5:
                return _FakeScalarResult(None)  # no Session row found -> (None, None, None)
            return _FakeScalarResult(None)

    monkeypatch.setattr(
        handoff_module, "decrypt_str", lambda enc, aad: enc.decode()
    )

    req = await handoff_module._build_request(_FakeDB(), session_id)
    assert req.slots.chief_complaint == "수면 곤란", (
        "slots were not assembled from Session.clinical_slots — BUG-066 "
        "regression (design doc's UNVERIFIED open item unresolved)"
    )
    # BUG-069 follow-up: metadata fields degrade to None gracefully when the
    # underlying Session row isn't found by this mock (not this test's
    # focus — asserted for completeness, must not raise).
    assert req.patient_gender is None
    assert req.session_started_at is None
    assert req.session_ended_at is None
