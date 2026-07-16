"""BUG-031 regression tests — F2 per-candidate validation + panic enum.

`error.md` BUG-031: the ORIGINAL `DomainInferenceAgent._parse` validated the
whole `DomainInferenceLLMResponse` atomically — one malformed
`domain_candidates[i]` field (an out-of-enum `domain` literal, a malformed
`evidence[]` item) dropped EVERY candidate in the same response, not just
the offending one (EXP-025: 10/72 sessions, 32 field errors, all 10
sessions' `domain_candidates` degraded to `[]`).

This file covers the developer-lane fix directions the BUG-031 entry itself
named:
1. Per-candidate validation — `_parse`/`_salvage_domain_candidates` keep
   every candidate that validates, drop (with logged, indexed reason) only
   the ones that don't.
2. `panic` added to `DomainName` (8 -> 9 values) — the concrete, observed
   `literal_error` trigger (VP-004's `fluctuating_panic_recurrence` arc).
"""

from __future__ import annotations

import json

from src.agents.domain_inference import DomainInferenceAgent
from src.schemas.domain_inference import DomainCandidate, DomainName


def _candidate_dict(domain: str = "anxiety", *, source_type: str = "utterance") -> dict:
    return {
        "domain": domain,
        "confidence": 0.7,
        "evidence": [
            {"source_type": source_type, "source_id": "turn_1", "quote": "불안해요"}
        ],
    }


class TestPanicDomainEnum:
    """BUG-031 trigger 1 — `domain="panic"` used to be a bare literal_error."""

    def test_panic_accepted_by_domain_candidate(self) -> None:
        cand = DomainCandidate(**_candidate_dict(domain="panic"))
        assert cand.domain == "panic"

    def test_domain_name_has_nine_values(self) -> None:
        assert set(DomainName.__args__) == {  # type: ignore[attr-defined]
            "anxiety", "depression", "alcohol", "substance", "trauma",
            "sleep", "psychosis", "other", "panic",
        }

    def test_panic_maps_to_gad7(self) -> None:
        from src.rag.questionnaire_mapping import (
            DOMAIN_TO_SCALE,
            resolve_questionnaire_for_domain_name,
        )

        assert DOMAIN_TO_SCALE["panic"] == "GAD-7"
        assert resolve_questionnaire_for_domain_name("panic") == "GAD-7"
        # Same anxiety-family precedent as the native "anxiety" domain.
        assert DOMAIN_TO_SCALE["panic"] == DOMAIN_TO_SCALE["anxiety"]


class TestPerCandidateSalvage:
    """BUG-031 trigger 1/2 — one malformed candidate no longer zeroes out
    every valid candidate in the same response."""

    def test_atomic_validation_still_used_on_a_clean_response(self) -> None:
        """No behavior change on a fully valid response — parsed via the
        fast atomic path, reason/validation_errors empty."""
        content = json.dumps(
            {
                "domain_candidates": [_candidate_dict("anxiety"), _candidate_dict("sleep")],
                "department_candidates": [],
                "summary": "ok",
            }
        )
        parsed, reason, errors = DomainInferenceAgent._parse(content)
        assert parsed is not None
        assert len(parsed.domain_candidates) == 2
        assert reason == ""
        assert errors is None

    def test_one_bad_candidate_no_longer_drops_the_valid_one(self) -> None:
        """The exact BUG-031 shape: candidates[1].domain is out-of-enum
        (mirrors the observed live "panic"-before-the-enum-fix case with a
        still-genuinely-invalid value) — candidates[0] must survive."""
        good = _candidate_dict("anxiety")
        bad = _candidate_dict("not_a_real_domain")
        content = json.dumps(
            {
                "domain_candidates": [good, bad],
                "department_candidates": [],
                "summary": "ok",
            }
        )
        parsed, reason, errors = DomainInferenceAgent._parse(content)
        assert parsed is not None, "candidates[0] should have survived salvage"
        assert len(parsed.domain_candidates) == 1
        assert parsed.domain_candidates[0].domain == "anxiety"
        assert "salvage" in reason.lower() or "partial" in reason.lower()
        assert errors is not None
        assert len(errors) >= 1
        assert errors[0]["domain_candidates_index"] == 1

    def test_malformed_evidence_source_type_drops_only_that_candidate(self) -> None:
        """BUG-031 trigger 2: a merged/mistyped evidence source_type on one
        candidate must not sink a sibling candidate's clean evidence.

        Uses a merged-key shape ("case_card:903:quote") that neither
        BUG-019's DB-table-origin coercion nor BUG-045's clinical-slot-name
        coercion recovers (both are narrow-by-design) — still genuinely
        malformed, unlike a bare slot name ("chief_complaint"), which
        BUG-045 now coerces to "utterance" and legitimately survives (see
        `tests/repro/test_bug_045.py`, which covers that recovery path)."""
        good = _candidate_dict("sleep")
        bad = {
            "domain": "depression",
            "confidence": 0.6,
            "evidence": [
                {
                    "source_type": "case_card:903:quote",  # merged key, not a real enum value
                    "source_id": "turn_2",
                    "quote": "우울해요",
                }
            ],
        }
        content = json.dumps(
            {"domain_candidates": [good, bad], "department_candidates": [], "summary": ""}
        )
        parsed, reason, errors = DomainInferenceAgent._parse(content)
        assert parsed is not None
        assert len(parsed.domain_candidates) == 1
        assert parsed.domain_candidates[0].domain == "sleep"
        assert errors is not None and errors[0]["domain_candidates_index"] == 1

    def test_all_candidates_malformed_degrades_exactly_like_pre_fix(self) -> None:
        """Nothing survives salvage -> parsed=None, same atomic-failure
        shape the pre-fix code always returned."""
        bad1 = _candidate_dict("not_a_real_domain")
        bad2 = _candidate_dict("also_not_real")
        content = json.dumps(
            {"domain_candidates": [bad1, bad2], "department_candidates": [], "summary": ""}
        )
        parsed, reason, errors = DomainInferenceAgent._parse(content)
        assert parsed is None
        assert "schema validation failure" in reason
        assert errors is not None and len(errors) >= 2

    def test_malformed_field_outside_domain_candidates_still_fails_atomically(self) -> None:
        """The salvage is scoped to domain_candidates only (BUG-031's two
        named trigger classes) — a malformed department_candidates entry
        alongside a salvageable domain_candidates list still degrades to
        None, per the entry's own scoping."""
        good = _candidate_dict("anxiety")
        content = json.dumps(
            {
                "domain_candidates": [good],
                "department_candidates": [{"department": "", "reason": ""}],  # min_length=1 fails
                "summary": "",
            }
        )
        parsed, reason, errors = DomainInferenceAgent._parse(content)
        assert parsed is None
        assert "recovered 1/1 domain_candidates" in reason
        assert errors is not None

    def test_json_parse_failure_unaffected_by_salvage_path(self) -> None:
        """A malformed JSON body never reaches the salvage logic — same
        JSON-parse-failure branch as before, validation_errors stays None."""
        parsed, reason, errors = DomainInferenceAgent._parse("not json{")
        assert parsed is None
        assert "JSON parse failure" in reason
        assert errors is None

    def test_missing_domain_candidates_key_has_nothing_to_salvage(self) -> None:
        """A response failing validation for a reason unrelated to
        domain_candidates (e.g. domain_candidates absent entirely) has
        nothing to salvage from — degrades exactly like pre-fix."""
        content = json.dumps({"domain_candidates": "not-a-list", "summary": ""})
        parsed, reason, errors = DomainInferenceAgent._parse(content)
        assert parsed is None
        assert errors is not None


class TestSalvageHelperDirectly:
    def test_salvage_returns_empty_for_non_dict_data(self) -> None:
        salvaged, dropped = DomainInferenceAgent._salvage_domain_candidates([1, 2, 3])
        assert salvaged == []
        assert dropped == []

    def test_salvage_returns_empty_when_domain_candidates_not_a_list(self) -> None:
        salvaged, dropped = DomainInferenceAgent._salvage_domain_candidates(
            {"domain_candidates": {"not": "a list"}}
        )
        assert salvaged == []
        assert dropped == []

    def test_salvage_keeps_valid_drops_invalid_with_index(self) -> None:
        data = {
            "domain_candidates": [
                _candidate_dict("anxiety"),
                _candidate_dict("bogus"),
                _candidate_dict("sleep"),
            ]
        }
        salvaged, dropped = DomainInferenceAgent._salvage_domain_candidates(data)
        assert [c.domain for c in salvaged] == ["anxiety", "sleep"]
        assert len(dropped) == 1
        assert dropped[0]["domain_candidates_index"] == 1
