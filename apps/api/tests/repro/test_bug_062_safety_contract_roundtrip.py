"""Regression test for BUG-062 (fixed this pass, EXP-031 fix_wave_design.md
Option B). No live HTTP — pure contract/translation-layer test.

Pre-fix: `contracts.safety.SafetyRequest`/`SafetyResponse` (apps/api's
shared-contract vocabulary) shared no field names with ai-server's real
`/ai/safety/classify` schema (`SafetyInput`: session_id/user_message/
conversation_history; `SafetyOutput`: risk_level/categories/flagged_phrases/
confidence/ctrs_level/requires_human_review/crisis_protocol_activated) — a
raw `SafetyRequest`-shaped body 422'd immediately. `ai_client.py`'s hand-
built adapter mitigated live traffic but left the shared contract itself
wrong (its own docstring's "single source of truth" claim was false).

Fix (this pass): `SafetyRequest`/`SafetyResponse` are now field-identical to
`SafetyInput`/`SafetyOutput`. `AIClient.safety_classify` is a plain generic
`_post` call (no more hand-built dict). The category-priority mapping that
used to live inline in `ai_client.py` is now `services/safety.py::
to_safety_assessment` (translating the wire response into the platform's
internal `SafetyAssessment`), single-sourced with the CVR-051 orchestrator-
crisis category map (`services/safety.py::map_crisis_category`/
`CRISIS_CATEGORY_PRIORITY`, now imported by `services/chat.py` instead of
keeping its own copy)."""

from __future__ import annotations

import inspect

import pytest
from contracts.safety import RiskCategory, RiskLevel, SafetyRequest, SafetyResponse
from pydantic import ValidationError


def test_safety_request_matches_ai_server_safety_input_field_names():
    """`SafetyRequest.model_dump()`'s field names must intersect FULLY with
    ai-server's real `SafetyInput` wire fields (`session_id`, `user_message`,
    `conversation_history` — plus the shared `AgentInput` base's
    `request_id`/`extra`, which `SafetyRequest` deliberately omits since
    apps/api never needs to set them — this is fine because `SafetyInput`
    does NOT require them: both have defaults)."""
    req = SafetyRequest(
        session_id="s-1", user_message="hello", conversation_history=[]
    )
    dumped = req.model_dump(mode="json")
    ai_server_safety_input_fields = {"session_id", "user_message", "conversation_history"}
    assert ai_server_safety_input_fields.issubset(dumped.keys()), (
        f"SafetyRequest field names {set(dumped.keys())!r} do not cover "
        f"ai-server's real SafetyInput fields {ai_server_safety_input_fields!r} "
        "— BUG-062 regression (this is what silently 422'd pre-fix)"
    )
    # extra=forbid on the wire — no stray platform-only fields would survive
    # a real ai-server round trip either (defensive, mirrors the 422 ai-
    # server itself would now give if this contract drifted again).
    with pytest.raises(ValidationError):
        SafetyRequest(session_id="s-1", user_message="hello", message="pre-fix-field")


def test_safety_output_shaped_dict_validates_against_safety_response():
    """A `SafetyOutput`-shaped dict (ai-server's real response, including the
    shared `AgentOutput` base fields it also carries) must validate against
    `SafetyResponse` without raising — this is what 422'd/mismatched
    pre-fix (the old `SafetyResponse` required `level`/`category`/
    `evidence`/`latency_ms`, none of which ai-server's real output has)."""
    ai_server_safety_output = {
        # AgentOutput base fields ai-server's real response also carries —
        # SafetyResponse must NOT reject these (extra="ignore", not forbid).
        "model_used": "solar-pro3",
        "prompt_version": "v1",
        "latency_ms": 42.0,
        "reason_summary": "no risk detected",
        "prompts_degraded": False,
        # SafetyOutput's own fields.
        "risk_level": "high",
        "categories": ["suicidal_ideation"],
        "flagged_phrases": ["죽고 싶다"],
        "confidence": 0.91,
        "rule_triggered": True,
        "llm_risk_level": "high",
        "rule_risk_level": "high",
        "ctrs_level": 2,
        "requires_human_review": True,
        "crisis_protocol_activated": True,
    }
    wire = SafetyResponse.model_validate(ai_server_safety_output)
    assert wire.risk_level == "high"
    assert wire.categories == ["suicidal_ideation"]
    assert wire.ctrs_level == 2
    assert wire.requires_human_review is True


def test_to_safety_assessment_translates_wire_into_platform_vocabulary():
    from src.services.safety import to_safety_assessment

    wire = SafetyResponse(
        risk_level="high",
        categories=["suicidal_ideation"],
        flagged_phrases=["죽고 싶다"],
        confidence=0.9,
        ctrs_level=2,
        requires_human_review=True,
        crisis_protocol_activated=True,
    )
    assessment = to_safety_assessment(wire)
    assert assessment.level == RiskLevel.HIGH
    assert assessment.category == RiskCategory.SUICIDE
    assert assessment.evidence.matched_keywords == ["죽고 싶다"]


def test_to_safety_assessment_maps_none_risk_level_to_low():
    """ai-server's `RiskLevel` has a `"none"` tier `contracts.safety.
    RiskLevel` does not — must collapse to LOW, not raise/KeyError."""
    from src.services.safety import to_safety_assessment

    wire = SafetyResponse(risk_level="none", categories=[])
    assessment = to_safety_assessment(wire)
    assert assessment.level == RiskLevel.LOW
    assert assessment.category == RiskCategory.NONE


def test_ai_client_safety_classify_is_generic_post_not_hand_built():
    """BUG-062 interim-mitigation retirement check: `AIClient.safety_classify`
    must no longer hand-build the ai-server request body / hand-map the
    response — it should be the same one-line generic `_post` pattern every
    other endpoint uses."""
    from src.services.ai_client import AIClient

    source = inspect.getsource(AIClient.safety_classify)
    assert "self._post(" in source, (
        "safety_classify no longer uses the generic _post path — interim "
        "adapter retirement regression"
    )
    assert '"session_id": "platform-safety-gate"' not in source, (
        "safety_classify still hand-builds the request body — the interim "
        "BUG-062 adapter was not actually retired"
    )


def test_category_priority_single_sourced_between_safety_and_chat():
    """BUG-062 fix wave directive: the category-priority map must be a
    SINGLE source, shared by the pre-gate safety-classify translation and
    the CVR-051 orchestrator-crisis path (`services/chat.py`) — not two
    independently-maintained copies."""
    from src.services import chat as chat_module
    from src.services import safety as safety_module

    # chat.py must import the shared map, not declare its own.
    assert not hasattr(chat_module, "_CRISIS_CATEGORY_PRIORITY"), (
        "services/chat.py still declares its own _CRISIS_CATEGORY_PRIORITY "
        "— single-source relocation regression"
    )
    assert chat_module.map_crisis_category is safety_module.map_crisis_category
