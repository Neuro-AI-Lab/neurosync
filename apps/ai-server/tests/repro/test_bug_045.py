"""BUG-045 regression tests — `evidence[].source_type` clinical-slot-name
collision (qa Stage-D finding, VP-004 EXP-025 artifacts).

Distinct from BUG-019's DB-table-origin collision ("case_card"/"qa" ->
"rag_chunk"): the model sometimes echoes a CLINICAL SLOT NAME
(`src.agents.clinical_slot.ALL_SLOT_KEYS`) into `evidence[].source_type`
instead of the required `Literal["rag_chunk", "utterance", "ocr_document"]`
— e.g. `"chief_complaint"`/`"history_of_present_illness"`, observed live in
VP-004 EXP-025's `domain_inference.json` artifacts and documented as an
out-of-scope trigger class in BUG-031's own root-cause writeup. Every
offending value is slot-content-derived (the evidence item is quoting
patient utterance content classified under that slot), so the correct
coercion target is `"utterance"`, NOT `"rag_chunk"`.
"""

from __future__ import annotations

import pytest

from src.agents.clinical_slot import ALL_SLOT_KEYS
from src.agents.domain_inference import (
    _SOURCE_TYPE_SLOT_NAME_RE,
    _normalize_source_type_collision,
)
from src.schemas.domain_inference import DomainInferenceLLMResponse


def _response_dict(source_type: str, *, source_id: str = "turn_3") -> dict:
    return {
        "domain_candidates": [
            {
                "domain": "depression",
                "confidence": 0.7,
                "evidence": [
                    {
                        "source_type": source_type,
                        "source_id": source_id,
                        "quote": "요즘 계속 우울해요",
                    }
                ],
            }
        ],
        "department_candidates": [],
        "summary": "test",
    }


class TestSlotNameCoercion:
    """Every one of the 12 standard slot keys coerces to 'utterance'."""

    @pytest.mark.parametrize("slot_key", ALL_SLOT_KEYS)
    def test_bare_slot_key_coerces_to_utterance(self, slot_key: str) -> None:
        data = _response_dict(slot_key)
        out = _normalize_source_type_collision(data)
        assert out["domain_candidates"][0]["evidence"][0]["source_type"] == "utterance"

    def test_slot_key_with_digit_suffix_coerces(self) -> None:
        data = _response_dict("chief_complaint:12")
        out = _normalize_source_type_collision(data)
        assert out["domain_candidates"][0]["evidence"][0]["source_type"] == "utterance"

    def test_history_of_present_illness_coerces(self) -> None:
        # Verbatim live-observed value (VP-004 EXP-025, BUG-031's own writeup).
        data = _response_dict("history_of_present_illness")
        out = _normalize_source_type_collision(data)
        assert out["domain_candidates"][0]["evidence"][0]["source_type"] == "utterance"

    def test_coerced_response_now_validates(self) -> None:
        """The whole point: a response that previously raised ValidationError
        on this evidence item now validates cleanly."""
        data = _normalize_source_type_collision(_response_dict("risk_assessment"))
        parsed = DomainInferenceLLMResponse.model_validate(data)
        assert parsed.domain_candidates[0].evidence[0].source_type == "utterance"


class TestNoCrossContamination:
    """BUG-019's DB-table-origin collision must still coerce to 'rag_chunk',
    never 'utterance' — the two collision classes must not share targets."""

    def test_db_table_origin_still_coerces_to_rag_chunk(self) -> None:
        data = _normalize_source_type_collision(_response_dict("qa:1502"))
        assert data["domain_candidates"][0]["evidence"][0]["source_type"] == "rag_chunk"

    def test_case_card_still_coerces_to_rag_chunk(self) -> None:
        data = _normalize_source_type_collision(_response_dict("case_card"))
        assert data["domain_candidates"][0]["evidence"][0]["source_type"] == "rag_chunk"


class TestNarrowScope:
    """Genuinely malformed/already-valid values are left untouched."""

    @pytest.mark.parametrize("value", ["rag_chunk", "utterance", "ocr_document"])
    def test_already_valid_values_untouched(self, value: str) -> None:
        data = _normalize_source_type_collision(_response_dict(value))
        assert data["domain_candidates"][0]["evidence"][0]["source_type"] == value

    def test_genuinely_malformed_value_left_alone_and_still_fails(self) -> None:
        data = _normalize_source_type_collision(_response_dict("garbage"))
        assert data["domain_candidates"][0]["evidence"][0]["source_type"] == "garbage"
        with pytest.raises(ValueError):
            DomainInferenceLLMResponse.model_validate(data)

    def test_slot_name_regex_does_not_match_non_slot_strings(self) -> None:
        assert _SOURCE_TYPE_SLOT_NAME_RE.match("rag_chunk") is None
        assert _SOURCE_TYPE_SLOT_NAME_RE.match("garbage") is None
        assert _SOURCE_TYPE_SLOT_NAME_RE.match("chief_complaint_extra") is None
