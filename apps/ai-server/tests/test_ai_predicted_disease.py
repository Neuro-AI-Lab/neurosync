"""Basic contract/smoke tests for the "AI 예상질환" container schema —
Track B, PLAN-2026-W28-H, REV-013 §3/§4.

This is the "basic unit test for the container schema" this mission's brief
scopes to developer. The adversarial HPI-isolation/no-leak live-behavior
test suite (injecting `AIPredictedDiseaseOutput` into `state` and asserting
`report_markdown` never contains it, plus the `AgentInput.extra`/
`state.conversation_history` channel regression tests REV-013 §3 names) is
qa's Wave-4 deliverable and is intentionally NOT duplicated here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.ai_predicted_disease import (
    AI_PREDICTED_DISEASE_DISCLAIMER_KO,
    AIPredictedDiseaseCandidate,
    AIPredictedDiseaseOutput,
)


class TestAIPredictedDiseaseCandidate:
    def test_minimal_valid_candidate(self) -> None:
        c = AIPredictedDiseaseCandidate(disease="공황장애", similarity_score=0.42)
        assert c.disease == "공황장애"
        assert c.similarity_score == 0.42

    def test_similarity_score_bounded_0_to_1(self) -> None:
        with pytest.raises(ValidationError):
            AIPredictedDiseaseCandidate(disease="x", similarity_score=1.1)
        with pytest.raises(ValidationError):
            AIPredictedDiseaseCandidate(disease="x", similarity_score=-0.01)

    def test_similarity_score_boundary_values_ok(self) -> None:
        lo = AIPredictedDiseaseCandidate(disease="x", similarity_score=0.0)
        hi = AIPredictedDiseaseCandidate(disease="x", similarity_score=1.0)
        assert lo.similarity_score == 0.0
        assert hi.similarity_score == 1.0

    def test_disease_required_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            AIPredictedDiseaseCandidate(disease="", similarity_score=0.5)

    def test_extra_forbid_rejects_unknown_field(self) -> None:
        """REV-013 §3 type layer: `extra="forbid"`, not Pydantic's default
        `extra="ignore"` — an unexpected field (e.g. a future 'probability'
        alias smuggled in by mistake) raises, it is not silently dropped."""
        with pytest.raises(ValidationError):
            AIPredictedDiseaseCandidate(
                disease="x", similarity_score=0.5, probability=0.9  # type: ignore[call-arg]
            )

    def test_field_name_is_similarity_score_not_probability_or_confidence(self) -> None:
        """REV-013 §4 labeling ruling made concrete: the licensed field name
        exists; the prohibited aliases do not exist as fields at all."""
        fields = AIPredictedDiseaseCandidate.model_fields
        assert "similarity_score" in fields
        assert "probability" not in fields
        assert "confidence" not in fields


class TestAIPredictedDiseaseCandidateProvenance:
    """ADR-020 condition 2 (REV-016(b) binding condition 2) — `source_id`/
    `quote` provenance fields, PLAN-2026-W28-K Task 3."""

    def test_provenance_fields_exist_and_default_to_none(self) -> None:
        """Optional at the schema level (default None) — see module
        docstring for the backward-compat rationale (pre-existing callers,
        e.g. `tests/test_hpi_isolation.py`'s synthetic-marker fixture, and
        the experimental_unpopulated empty-candidates convention). The "no
        evidence, no candidate" discipline is enforced at the
        population-code level in `f2.py`, not by making these fields
        schema-required."""
        fields = AIPredictedDiseaseCandidate.model_fields
        assert "source_id" in fields
        assert "quote" in fields
        c = AIPredictedDiseaseCandidate(disease="x", similarity_score=0.5)
        assert c.source_id is None
        assert c.quote is None

    def test_provenance_fields_populate_correctly_when_supplied(self) -> None:
        c = AIPredictedDiseaseCandidate(
            disease="공황장애", similarity_score=0.82,
            source_id="case_card:687", quote="발작이 오면 숨을 못 쉬어요",
        )
        assert c.source_id == "case_card:687"
        assert c.quote == "발작이 오면 숨을 못 쉬어요"

    def test_provenance_fields_reject_empty_string(self) -> None:
        """min_length=1 when a value IS supplied — an empty-string
        `source_id`/`quote` is not a legitimate 'no provenance' signal
        (`None` is what represents that)."""
        with pytest.raises(ValidationError):
            AIPredictedDiseaseCandidate(
                disease="x", similarity_score=0.5, source_id="", quote="q"
            )
        with pytest.raises(ValidationError):
            AIPredictedDiseaseCandidate(
                disease="x", similarity_score=0.5, source_id="case_card:1", quote=""
            )


class TestAIPredictedDiseaseOutput:
    def test_experimental_unpopulated_container(self) -> None:
        out = AIPredictedDiseaseOutput(
            mode="experimental_unpopulated",
            reason_summary="RAG-arm EXPERIMENTAL pending ADR-016 lift — "
            "AI-disease container not yet live-populated",
        )
        assert out.candidates == []
        assert out.mode == "experimental_unpopulated"
        assert out.is_diagnostic is False
        assert out.disclaimer == AI_PREDICTED_DISEASE_DISCLAIMER_KO

    def test_is_diagnostic_default_false(self) -> None:
        out = AIPredictedDiseaseOutput(mode="experimental_unpopulated")
        assert out.is_diagnostic is False

    def test_is_diagnostic_literal_false_cannot_be_widened_at_runtime(self) -> None:
        """REV-013 §4(c): assert the `Literal[False]` TYPE, not just the
        default value — constructing with `is_diagnostic=True` must fail
        validation, not silently succeed."""
        with pytest.raises(ValidationError):
            AIPredictedDiseaseOutput(
                mode="experimental_unpopulated", is_diagnostic=True  # type: ignore[arg-type]
            )

    def test_is_diagnostic_field_annotation_is_literal_false(self) -> None:
        """Confirms the annotation is a `Literal[False]`, not a plain `bool`
        that merely defaults to `False` — the type itself is what rejects
        `True` (checked in the previous test)."""
        annotation = AIPredictedDiseaseOutput.model_fields["is_diagnostic"].annotation
        assert "Literal" in str(annotation) and "False" in str(annotation), annotation

    def test_mode_restricted_to_licensed_literals(self) -> None:
        with pytest.raises(ValidationError):
            AIPredictedDiseaseOutput(mode="rag_llm_only_guess")  # type: ignore[arg-type]

    def test_rag_live_mode_accepted_by_schema(self) -> None:
        """The schema permits `mode="rag_live"` (shape only) — this test
        does not assert anything about whether live population is actually
        wired; that gate lives in `f2.py`'s `_build_ai_predicted_disease`
        (ADR-016) and qa's Wave-4 suite, not in the schema layer."""
        out = AIPredictedDiseaseOutput(mode="rag_live")
        assert out.mode == "rag_live"

    def test_max_five_candidates(self) -> None:
        six = [
            AIPredictedDiseaseCandidate(disease=f"d{i}", similarity_score=0.1) for i in range(6)
        ]
        with pytest.raises(ValidationError):
            AIPredictedDiseaseOutput(mode="rag_live", candidates=six)

    def test_five_candidates_ok(self) -> None:
        five = [
            AIPredictedDiseaseCandidate(disease=f"d{i}", similarity_score=0.1) for i in range(5)
        ]
        out = AIPredictedDiseaseOutput(mode="rag_live", candidates=five)
        assert len(out.candidates) == 5

    def test_extra_forbid_on_output_too(self) -> None:
        with pytest.raises(ValidationError):
            AIPredictedDiseaseOutput(
                mode="experimental_unpopulated", probability=0.5  # type: ignore[call-arg]
            )

    def test_no_softmax_normalization_no_such_method_or_field(self) -> None:
        """REV-013 §4(b): the container never computes/exposes a normalized
        top-5 view — two independent, out-of-range-by-construction scores
        both survive untouched, with nothing on the model that sums or
        rescales them."""
        out = AIPredictedDiseaseOutput(
            mode="rag_live",
            candidates=[
                AIPredictedDiseaseCandidate(disease="a", similarity_score=0.9),
                AIPredictedDiseaseCandidate(disease="b", similarity_score=0.85),
            ],
        )
        scores = [c.similarity_score for c in out.candidates]
        assert scores == [0.9, 0.85]
        assert sum(scores) != 1.0  # not normalized to sum to 1
        assert not hasattr(out, "normalized_scores")
        assert not hasattr(out, "softmax_scores")


class TestRecommendedQuestionnaireField:
    """Container field, PLAN-2026-W28-Q W5 (plan §3 "Disease questionnaire
    linkage" row / §9 answer #5a). Population-correctness (mapping content,
    derivation from candidates) is `f2.py`'s and
    `tests/test_f2_pipeline.py`/`tests/test_questionnaire_mapping.py`'s
    concern; this class covers the schema-layer contract only."""

    def test_defaults_to_none(self) -> None:
        out = AIPredictedDiseaseOutput(mode="experimental_unpopulated")
        assert out.recommended_questionnaire is None

    def test_accepts_each_supported_scale_name(self) -> None:
        for scale in ("PHQ-9", "GAD-7", "PHQ-4", "WHO-5", "AUDIT-C"):
            out = AIPredictedDiseaseOutput(mode="rag_live", recommended_questionnaire=scale)
            assert out.recommended_questionnaire == scale

    def test_rejects_a_scale_name_outside_the_licensed_literal(self) -> None:
        with pytest.raises(ValidationError):
            AIPredictedDiseaseOutput(
                mode="rag_live", recommended_questionnaire="MADRS"  # type: ignore[arg-type]
            )

    def test_field_present_on_model_fields(self) -> None:
        assert "recommended_questionnaire" in AIPredictedDiseaseOutput.model_fields

    def test_none_survives_model_dump(self) -> None:
        out = AIPredictedDiseaseOutput(mode="experimental_unpopulated")
        assert out.model_dump()["recommended_questionnaire"] is None

    def test_populated_value_survives_model_dump(self) -> None:
        out = AIPredictedDiseaseOutput(mode="rag_live", recommended_questionnaire="AUDIT-C")
        assert out.model_dump()["recommended_questionnaire"] == "AUDIT-C"


class TestStandaloneModule:
    """REV-013 §3: this module shares no base class/field/inheritance with
    SlotData/HandoffInput/HandoffOutput/DomainCandidate."""

    def test_no_shared_base_or_field_with_handoff_or_domain_inference_schemas(self) -> None:
        from src.schemas.domain_inference import DomainCandidate
        from src.schemas.handoff import HandoffInput, HandoffOutput, SlotData

        for other in (SlotData, HandoffInput, HandoffOutput, DomainCandidate):
            assert not issubclass(AIPredictedDiseaseOutput, other)
            assert not issubclass(AIPredictedDiseaseCandidate, other)
            assert other not in AIPredictedDiseaseOutput.__mro__
            assert other not in AIPredictedDiseaseCandidate.__mro__

    def test_module_does_not_import_handoff_or_domain_inference_schemas(self) -> None:
        import inspect

        import src.schemas.ai_predicted_disease as mod

        source = inspect.getsource(mod)
        assert "schemas.handoff" not in source
        assert "schemas.domain_inference" not in source
        assert "agents.orchestrator" not in source
        assert "agents.handoff_generator" not in source
