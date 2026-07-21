"""Exact-source grounding and direct-assertion policy tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from contracts.handoff import Citation, HandoffRequest
from pydantic import BaseModel, Field

from src.services.handoff_claim_guard import handoff_claims_are_valid

_MESSAGE_ID = UUID("22222222-2222-4222-8222-222222222222")


class _Activity(BaseModel):
    sleep: str | None = None
    appetite: str | None = None
    activity: str | None = None


class _Claims(BaseModel):
    chief_complaint: str = ""
    present_illness: str = ""
    symptoms: list[str] = Field(default_factory=list)
    onset: str | None = None
    recent_changes: str | None = None
    triggers: list[str] = Field(default_factory=list)
    sleep_appetite_activity: _Activity = Field(default_factory=_Activity)
    psych_history: str | None = None
    medications: str | None = None
    documents_summary: list[str] = Field(default_factory=list)
    clinician_attention: list[str] = Field(default_factory=list)
    evidence: list[Citation] = Field(default_factory=list)


def _request(content: str, role: str = "user") -> HandoffRequest:
    return HandoffRequest.model_validate(
        {
            "session_id": "11111111-1111-4111-8111-111111111111",
            "messages": [
                {"message_id": str(_MESSAGE_ID), "role": role, "content": content}
            ],
        }
    )


def _claim(field_name: str, value: str, *, quote: str | None = None) -> _Claims:
    evidence = [
        Citation(
            field=field_name,
            source_message_id=_MESSAGE_ID,
            quote=value if quote is None else quote,
        )
    ]
    if field_name == "psych_history":
        return _Claims(psych_history=value, evidence=evidence)
    if field_name == "medications":
        return _Claims(medications=value, evidence=evidence)
    if field_name == "clinician_attention[0]":
        return _Claims(clinician_attention=[value], evidence=evidence)
    return _Claims(chief_complaint=value, evidence=evidence)


@pytest.mark.parametrize(
    "claim",
    [
        "불안장애로 판단됩니다.",
        "세르트랄린을 투여하세요.",
        "diagnose patient with depression",
        "the diagnosis is depression",
        "환자는 우울증입니다.",
        "세르트랄린을 처방하세요.",
    ],
)
def test_rejects_exact_source_direct_diagnosis_or_treatment(claim: str) -> None:
    claims = _claim("clinician_attention[0]", claim)

    assert not handoff_claims_are_valid(claims, _request(claim))


@pytest.mark.parametrize(
    ("field_name", "claim"),
    [
        ("psych_history", "과거 우울증 진단을 받은 적이 있습니다."),
        ("psych_history", "과거 우울증으로 진단받았습니다."),
        ("medications", "현재 세르트랄린을 복용 중입니다."),
    ],
)
def test_accepts_reported_history_and_current_medication(
    field_name: str,
    claim: str,
) -> None:
    claims = _claim(field_name, claim)

    assert handoff_claims_are_valid(claims, _request(claim))


def test_rejects_partial_overlap_between_claim_and_quote() -> None:
    claims = _claim("chief_complaint", "불면", quote="불면 증상이 있습니다.")

    assert not handoff_claims_are_valid(claims, _request("불면 증상이 있습니다."))


def test_rejects_duplicate_citations_for_one_target() -> None:
    claim = "불면 증상이 있습니다."
    citation = Citation(
        field="chief_complaint",
        source_message_id=_MESSAGE_ID,
        quote=claim,
    )
    claims = _Claims(chief_complaint=claim, evidence=[citation, citation])

    assert not handoff_claims_are_valid(claims, _request(claim))


@pytest.mark.parametrize(
    ("content", "role"),
    [("불", "user"), ("불면 증상이 있습니다.", "assistant")],
)
def test_rejects_too_short_or_non_user_source(content: str, role: str) -> None:
    claims = _claim("chief_complaint", content)

    assert not handoff_claims_are_valid(claims, _request(content, role))
