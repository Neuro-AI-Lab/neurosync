"""src.f2 — pipeline-level offline tests (C-4), mock-based, no live LLM/DB.

Covers: llm_only fallback (Stage1 mock empty/failure -> mode=llm_only, no
rag_chunk evidence accepted downstream), is_first_visit inference, artifact/
report building on a stubbed agent output, and one full CLI (`--conversation`)
end-to-end smoke test with DomainInferenceAgent itself stubbed out (no live
LLM/DB anywhere in this file, per the C-4 mock-based constraint).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.f2 as f2
from src.eval.f2_grounding import (
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    audit_domain_candidates,
    filter_domain_candidates,
)
from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.domain_inference import (
    DepartmentCandidate,
    DomainCandidate,
    DomainEvidence,
    DomainInferenceOutput,
    RetrievalMeta,
    UtteranceTurn,
)


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class TestRunStage1:
    @pytest.mark.asyncio
    async def test_no_rag_flag_forces_llm_only(self) -> None:
        mode, chunks = await f2.run_stage1(
            {"chief_complaint": "불안"}, no_rag=True, k=3
        )
        assert mode == "llm_only"
        assert chunks == []

    @pytest.mark.asyncio
    async def test_empty_query_slots_forces_llm_only(self) -> None:
        mode, chunks = await f2.run_stage1({}, no_rag=False, k=3)
        assert mode == "llm_only"
        assert chunks == []

    @pytest.mark.asyncio
    async def test_db_failure_falls_back_to_llm_only_never_crashes(self, monkeypatch) -> None:
        def _boom() -> None:
            raise RuntimeError("connection refused — DB not configured")

        monkeypatch.setattr(f2, "get_sessionmaker", _boom)

        mode, chunks = await f2.run_stage1(
            {"chief_complaint": "불안감과 수면 문제"}, no_rag=False, k=3
        )
        assert mode == "llm_only"
        assert chunks == []

    @pytest.mark.asyncio
    async def test_successful_retrieval_reports_rag_mode(self, monkeypatch) -> None:
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))

        fake_chunks = [
            {
                "chunk_id": "case_card:1", "source_type": "case_card",
                "text": "불안 사례", "score": 0.9,
            }
        ]
        mock_retrieve = AsyncMock(return_value=fake_chunks)
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)

        mode, chunks = await f2.run_stage1(
            {"chief_complaint": "불안감과 수면 문제"}, no_rag=False, k=3
        )
        assert mode == "rag"
        assert chunks == fake_chunks


class TestVal010RiskAssessmentExcludedFromStage1Query:
    """VAL-010 code-level mitigation (REV-007 finding #3 / REV-010 finding
    3): `risk_assessment` (composed from the Safety Probe/SI-screen
    exchange, genuinely risk-worded by construction) must not be embedded
    verbatim as a Stage-1 retrieval query -- it systematically biased
    Stage-1 retrieval toward risk/crisis-topic chunks for higher-risk
    personas. chief_complaint/history_of_present_illness continue to drive
    retrieval unchanged."""

    def test_stage1_query_slots_excludes_risk_assessment(self) -> None:
        assert f2._STAGE1_QUERY_SLOTS == ("chief_complaint", "history_of_present_illness")
        assert "risk_assessment" not in f2._STAGE1_QUERY_SLOTS

    @pytest.mark.asyncio
    async def test_risk_worded_risk_assessment_not_embedded_as_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        mock_retrieve = AsyncMock(return_value=[])
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)

        risk_text = "살고 싶지 않다고 표현, 구체적 자살 계획 보고"
        final_slots = {
            "chief_complaint": "불안감과 수면 문제",
            "history_of_present_illness": "2주 전부터 악화",
            "risk_assessment": risk_text,
        }
        mode, chunks = await f2.run_stage1(final_slots, no_rag=False, k=3)

        assert mode == "rag"
        mock_retrieve.assert_awaited_once()
        called_queries = mock_retrieve.call_args.args[1]
        assert risk_text not in called_queries, (
            "VAL-010 regression: risk_assessment's risk-worded text was "
            "embedded verbatim as a Stage-1 retrieval query."
        )
        assert called_queries == ["불안감과 수면 문제", "2주 전부터 악화"]

    @pytest.mark.asyncio
    async def test_chief_complaint_only_still_composes_a_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legitimate clinical retrieval relevance is unaffected: a
        risk_assessment-only run (no chief_complaint/HPI) still falls back
        to llm_only as before (VAL-010 must not silently create RAG-mode
        queries out of thin air), and chief_complaint/HPI alone are
        sufficient to drive mode=rag."""
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        mock_retrieve = AsyncMock(return_value=[])
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)

        mode, chunks = await f2.run_stage1(
            {"risk_assessment": "자살사고 있음"}, no_rag=False, k=3
        )
        assert mode == "llm_only"
        mock_retrieve.assert_not_awaited()

        mode, chunks = await f2.run_stage1(
            {"chief_complaint": "불안감과 수면 문제"}, no_rag=False, k=3
        )
        assert mode == "rag"

    def test_queries_used_composition_in_cli_run_excludes_risk_assessment(self) -> None:
        """Mirrors `f2._run`'s `queries_used` composition (same
        `_STAGE1_QUERY_SLOTS` source of truth)."""
        final_slots = {
            "chief_complaint": "불안감과 수면 문제",
            "history_of_present_illness": "2주 전부터 악화",
            "risk_assessment": "자살사고 있음, 구체적 계획 보고",
        }
        queries_used = [
            final_slots[k] for k in f2._STAGE1_QUERY_SLOTS if final_slots.get(k)
        ]
        assert queries_used == ["불안감과 수면 문제", "2주 전부터 악화"]


class TestIsFirstVisitInference:
    def test_first_visit_default_when_no_marker(self) -> None:
        data = {"turns": [{"turn": 0, "agent_response": "안녕하세요! 사전문진을 시작합니다."}]}
        assert f2._infer_is_first_visit(data) is True

    def test_revisit_detected_from_greeting_marker(self) -> None:
        data = {
            "turns": [
                {"turn": 0, "agent_response": "안녕하세요! 지난번 상담 기록을 확인했습니다. ..."}
            ]
        }
        assert f2._infer_is_first_visit(data) is False

    def test_no_turns_defaults_to_first_visit(self) -> None:
        assert f2._infer_is_first_visit({}) is True


class TestLlmOnlyModeRejectsRagChunkEvidence:
    """C-4: 'llm_only fallback path (Stage1 mock empty -> mode=llm_only, no
    rag_chunk evidence accepted)' — even if the LLM hallucinates a rag_chunk
    citation while mode=llm_only, the whitelist has zero known chunk_ids and
    must reject it (fabrication-0 gate holds under the fallback path too)."""

    def test_rag_chunk_evidence_rejected_when_no_chunks_were_retrieved(self) -> None:
        candidate = DomainCandidate(
            domain="sleep", confidence=0.3,
            evidence=[
                DomainEvidence(
                    source_type="rag_chunk", source_id="case_card:1",
                    quote="근거 청크가 실제로는 검색되지 않았음",
                )
            ],
        )
        # mode=llm_only -> chunk_texts is empty (nothing was actually retrieved).
        verdicts, counts = audit_domain_candidates(
            [candidate], chunk_texts={}, utterances={"turn_0": "발화"}
        )
        assert counts[VERDICT_REJECTED_UNKNOWN_SOURCE] == 1
        assert all(not v.accepted for v in verdicts)


class TestBuildTurnsAndInput:
    def test_build_turns_skips_empty_patient_message(self) -> None:
        data = {"turns": [
            {"turn": 0, "patient_message": ""},
            {"turn": 1, "patient_message": "불안해요"},
        ]}
        turns = f2._build_turns(data)
        assert len(turns) == 1
        assert turns[0] == UtteranceTurn(turn=1, patient_message="불안해요")

    def test_build_input_carries_mode_and_chunks(self) -> None:
        data = {"final_slots": [{"key": "chief_complaint", "value": "불안"}], "turns": []}
        inp = f2._build_input(
            data, session_id="t", is_first_visit=True, scale_scores=[],
            mode="rag",
            raw_chunks=[{"chunk_id": "qa:1", "source_type": "qa", "text": "QA 본문", "score": 0.5}],
            queries_used=["불안"],
        )
        assert inp.retrieval_mode == "rag"
        assert inp.retrieved_chunks[0].chunk_id == "qa:1"
        assert inp.queries == ["불안"]


class TestArtifactAndReport:
    def _output(self) -> DomainInferenceOutput:
        return DomainInferenceOutput(
            model_used="test-model",
            prompt_version="v1",
            latency_ms=12.3,
            reason_summary="ok",
            domain_candidates=[
                DomainCandidate(
                    domain="sleep", confidence=0.5,
                    evidence=[
                        DomainEvidence(
                            source_type="utterance", source_id="turn_0", quote="잠을 잘 못 자요"
                        )
                    ],
                )
            ],
            department_candidates=[],
            summary="수면 문제 언급",
            retrieval_meta=RetrievalMeta(mode="llm_only", chunks_returned=0, chunk_ids=[]),
        )

    def test_build_artifact_and_report_roundtrip(self) -> None:
        output = self._output()
        chunk_texts: dict[str, str] = {}
        utterances = {"turn_0": "요즘 잠을 잘 못 자요"}
        filtered, verdicts, counts = filter_domain_candidates(
            output.domain_candidates, chunk_texts=chunk_texts, utterances=utterances
        )
        orphans = f2.find_orphan_departments(filtered, output.department_candidates)
        filter_summary = f2._build_filter_summary(
            candidates_before=output.domain_candidates, candidates_after=filtered, counts=counts
        )
        repro = {
            "git_head": "deadbeef", "model_used": "test-model", "prompt_version": "v1",
            "input_file": "x.json", "input_sha256": "abc", "mode": "llm_only",
            "latency_ms": 12.3, "generated_at": "2026-07-08T00:00:00",
        }
        artifact = f2._build_artifact(
            output=output, domain_candidates=filtered, repro=repro,
            chunk_texts=chunk_texts, utterances=utterances,
            verdicts=verdicts, counts=counts, filter_summary=filter_summary, orphans=orphans,
            session_id="t", persona_id="VP-001",
        )
        assert artifact["domain_candidates"][0]["domain"] == "sleep"
        assert artifact["whitelist_audit"]["counts"]["accepted"] == 1
        assert artifact["filter_summary"]["candidates_before"] == 1
        assert artifact["filter_summary"]["candidates_after"] == 1
        report = f2._build_report(artifact)
        assert "sleep" in report
        assert "git HEAD" in report
        assert "Grounding cascade" in report

    def test_report_renders_recommended_questionnaire_and_caveat_alongside(self) -> None:
        """CVR-003 Findings 1/3/4 (W5 addendum): both fields must reach
        f2.py's rendered report line for the AI-predicted-disease field —
        not just the JSON artifact. The caveat is rendered alongside
        (never in place of) the recommendation."""
        output = self._output()
        chunk_texts: dict[str, str] = {}
        utterances = {"turn_0": "요즘 잠을 잘 못 자요"}
        filtered, verdicts, counts = filter_domain_candidates(
            output.domain_candidates, chunk_texts=chunk_texts, utterances=utterances
        )
        orphans = f2.find_orphan_departments(filtered, output.department_candidates)
        filter_summary = f2._build_filter_summary(
            candidates_before=output.domain_candidates, candidates_after=filtered, counts=counts
        )
        repro = {
            "git_head": "deadbeef", "model_used": "test-model", "prompt_version": "v1",
            "input_file": "x.json", "input_sha256": "abc", "mode": "llm_only",
            "latency_ms": 12.3, "generated_at": "2026-07-08T00:00:00",
        }
        ai_disease = AIPredictedDiseaseOutput(
            mode="rag_live",
            candidates=[
                AIPredictedDiseaseCandidate(
                    disease="우울 삽화(우울증)", similarity_score=0.9,
                    source_id="case_card:1", quote="우울감",
                )
            ],
            reason_summary="1 disease candidate(s) derived...",
            recommended_questionnaire="PHQ-9",
            recommendation_caveat=(
                "PHQ-9 screens depressive-symptom burden only, does not "
                "screen manic/hypomanic symptoms — bipolar-spectrum "
                "presentations need clinician follow-up regardless of score."
            ),
        )
        artifact = f2._build_artifact(
            output=output, domain_candidates=filtered, repro=repro,
            chunk_texts=chunk_texts, utterances=utterances,
            verdicts=verdicts, counts=counts, filter_summary=filter_summary, orphans=orphans,
            session_id="t", persona_id="VP-001",
            ai_predicted_disease=ai_disease.model_dump(),
        )
        report = f2._build_report(artifact)

        assert "recommended_questionnaire: **PHQ-9**" in report
        assert "recommendation_caveat:" in report
        assert "manic/hypomanic symptoms" in report

    def test_report_omits_questionnaire_and_caveat_lines_when_both_none(self) -> None:
        """Additive/honest-only rendering: no noise lines when the run has
        no top candidate / no construct-valid mapping (e.g.
        experimental_unpopulated)."""
        output = self._output()
        chunk_texts: dict[str, str] = {}
        utterances = {"turn_0": "요즘 잠을 잘 못 자요"}
        filtered, verdicts, counts = filter_domain_candidates(
            output.domain_candidates, chunk_texts=chunk_texts, utterances=utterances
        )
        orphans = f2.find_orphan_departments(filtered, output.department_candidates)
        filter_summary = f2._build_filter_summary(
            candidates_before=output.domain_candidates, candidates_after=filtered, counts=counts
        )
        repro = {
            "git_head": "deadbeef", "model_used": "test-model", "prompt_version": "v1",
            "input_file": "x.json", "input_sha256": "abc", "mode": "llm_only",
            "latency_ms": 12.3, "generated_at": "2026-07-08T00:00:00",
        }
        ai_disease = AIPredictedDiseaseOutput(mode="experimental_unpopulated")
        artifact = f2._build_artifact(
            output=output, domain_candidates=filtered, repro=repro,
            chunk_texts=chunk_texts, utterances=utterances,
            verdicts=verdicts, counts=counts, filter_summary=filter_summary, orphans=orphans,
            session_id="t", persona_id="VP-001",
            ai_predicted_disease=ai_disease.model_dump(),
        )
        report = f2._build_report(artifact)

        assert "recommended_questionnaire:" not in report
        assert "recommendation_caveat:" not in report

    def test_save_f2_result_writes_json_and_report(self, tmp_path) -> None:
        output = self._output()
        filter_summary = f2._build_filter_summary(
            candidates_before=output.domain_candidates,
            candidates_after=output.domain_candidates,
            counts={"accepted": 0},
        )
        artifact = f2._build_artifact(
            output=output, domain_candidates=output.domain_candidates, repro={
                "git_head": "x", "model_used": "m", "prompt_version": "v1",
                "input_file": "x.json", "input_sha256": "y", "mode": "llm_only",
                "latency_ms": 1.0, "generated_at": "now",
            },
            chunk_texts={}, utterances={}, verdicts=[], counts={"accepted": 0},
            filter_summary=filter_summary,
            orphans=[], session_id="t", persona_id="VP-TEST",
        )
        paths = f2.save_f2_result(artifact, output_dir=tmp_path)
        assert paths["json"].exists()
        assert paths["report"].exists()
        assert paths["json"].name.endswith("_domain_inference.json")
        assert paths["report"].name.endswith("_report.md")


class TestFullCliSmoke:
    """Coding checklist 'smoke test passes' — the script runs end-to-end on
    synthetic data without error. DomainInferenceAgent is replaced by a stub
    (no live LLM); --no-rag means Stage 1 never touches a DB either."""

    @pytest.mark.asyncio
    async def test_run_end_to_end_conversation_flag_writes_artifact(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conversation = {
            "session_id": "f2_smoke",
            "persona_id": "VP-SMOKE",
            "persona_name": "테스트",
            "final_slots": [
                {"key": "chief_complaint", "value": "불안감과 수면 문제"},
                {"key": "history_of_present_illness", "value": "2주 전부터 악화"},
            ],
            "session_ctrs": 5,
            "crisis_triggered": False,
            "crisis_turn": None,
            "turns": [
                {"turn": 0, "patient_message": "요즘 잠을 잘 못 자요", "agent_response": "안녕"},
                {"turn": 1, "patient_message": "불안하기도 해요", "agent_response": "그렇군요"},
            ],
            "probe_events": [],
        }
        conv_path = tmp_path / "VP-SMOKE_20260708_000000_conversation.json"
        conv_path.write_text(json.dumps(conversation, ensure_ascii=False), encoding="utf-8")

        class _StubAgent:
            def __init__(self, model_router: object, prompt_loader: object) -> None:
                pass

            async def run(self, inp: object) -> DomainInferenceOutput:
                return DomainInferenceOutput(
                    model_used="stub", prompt_version="v1", latency_ms=5.0,
                    reason_summary="stub",
                    domain_candidates=[
                        DomainCandidate(
                            domain="sleep", confidence=0.4,
                            evidence=[
                                DomainEvidence(
                                    source_type="utterance", source_id="turn_0",
                                    quote="잠을 잘 못 자요",
                                )
                            ],
                        )
                    ],
                    department_candidates=[
                        DepartmentCandidate(
                            department="정신건강의학과", reason="수면 문제 지속", domain_ref="sleep"
                        )
                    ],
                    summary="수면 문제 언급",
                    retrieval_meta=RetrievalMeta(mode="llm_only", chunks_returned=0, chunk_ids=[]),
                )

        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            conversation=str(conv_path), persona=None, no_rag=True, k=3,
            out=str(out_dir), scale_scores=None, first_visit=False, revisit=False,
        )

        await f2._run(args)

        vp_dir = out_dir / "VP-SMOKE"
        json_files = list(vp_dir.glob("*_domain_inference.json"))
        report_files = list(vp_dir.glob("*_report.md"))
        assert len(json_files) == 1
        assert len(report_files) == 1

        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert artifact["retrieval_meta"]["mode"] == "llm_only"
        assert artifact["domain_candidates"][0]["domain"] == "sleep"
        assert artifact["whitelist_audit"]["counts"]["accepted"] == 1
        assert artifact["orphan_departments"] == []
        assert artifact["repro"]["input_file"] == str(conv_path)


class TestCascadeWiredIntoArtifact:
    """ADR-014 remediation — the artifact's `domain_candidates` must be the
    POST-cascade list (this is the open item the prior developer session
    escalated: `filter_domain_candidates` existed but `f2.py` still shipped
    raw, unstripped evidence in the saved JSON). Pipeline-level (stubbed
    agent, `f2._run` end-to-end), not just the pure-function unit tests in
    test_f2_grounding.py.
    """

    @staticmethod
    def _conversation(tmp_path, *, turns: list[dict]) -> Path:
        conversation = {
            "session_id": "f2_cascade",
            "persona_id": "VP-CASCADE",
            "persona_name": "테스트",
            "final_slots": [{"key": "chief_complaint", "value": "우울감 호소"}],
            "session_ctrs": 5,
            "crisis_triggered": False,
            "crisis_turn": None,
            "turns": turns,
            "probe_events": [],
        }
        conv_path = Path(tmp_path) / "VP-CASCADE_20260708_000000_conversation.json"
        conv_path.write_text(json.dumps(conversation, ensure_ascii=False), encoding="utf-8")
        return conv_path

    @staticmethod
    def _run_args(conv_path, out_dir) -> argparse.Namespace:
        return argparse.Namespace(
            conversation=str(conv_path), persona=None, no_rag=True, k=3,
            out=str(out_dir), scale_scores=None, first_visit=False, revisit=False,
        )

    @pytest.mark.asyncio
    async def test_only_risk_evidence_candidate_absent_from_artifact_not_just_flagged(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A candidate whose ONLY evidence is risk-lexicon content must be
        eliminated from the artifact's `domain_candidates` entirely — not
        merely flagged inline (that was the pre-wiring behavior, and is
        exactly the gap ADR-014 requires fixed in the LIVE pipeline output).
        The removal must be traceable via `filter_summary`, not silent.
        """
        risk_quote = "살고 싶지 않아요. 매일 밤 그 생각만 들어요."
        conv_path = self._conversation(
            tmp_path,
            turns=[{"turn": 0, "patient_message": risk_quote, "agent_response": "안녕"}],
        )

        class _StubAgent:
            def __init__(self, model_router: object, prompt_loader: object) -> None:
                pass

            async def run(self, inp: object) -> DomainInferenceOutput:
                return DomainInferenceOutput(
                    model_used="stub", prompt_version="v1", latency_ms=5.0,
                    reason_summary="stub",
                    domain_candidates=[
                        DomainCandidate(
                            domain="depression", confidence=0.6,
                            evidence=[
                                DomainEvidence(
                                    source_type="utterance", source_id="turn_0", quote=risk_quote
                                )
                            ],
                        )
                    ],
                    department_candidates=[],
                    summary="우울 호소",
                    retrieval_meta=RetrievalMeta(mode="llm_only", chunks_returned=0, chunk_ids=[]),
                )

        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(self._run_args(conv_path, out_dir))

        json_files = list((out_dir / "VP-CASCADE").glob("*_domain_inference.json"))
        report_files = list((out_dir / "VP-CASCADE").glob("*_report.md"))
        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))

        # NEITHER present in domain_candidates...
        assert artifact["domain_candidates"] == []
        assert not any(c["domain"] == "depression" for c in artifact["domain_candidates"])
        # ...NOR silently dropped: the delta is recorded in filter_summary.
        fs = artifact["filter_summary"]
        assert fs["candidates_before"] == 1
        assert fs["candidates_after"] == 0
        assert fs["candidates_eliminated"] == 1
        assert fs["eliminated_domains"] == ["depression"]
        assert fs["evidence_stripped"] == 1
        assert fs["evidence_stripped_risk_lexicon"] == 1
        # Full audit trail (incl. the specific reject reason) still preserved.
        assert artifact["whitelist_audit"]["counts"]["rejected_risk_lexicon"] == 1
        assert any(
            v["verdict"] == "rejected_risk_lexicon" and v["domain"] == "depression"
            for v in artifact["whitelist_audit"]["verdicts"]
        )

        report = report_files[0].read_text(encoding="utf-8")
        assert "ELIMINATED" in report
        assert "depression" in report

    @pytest.mark.asyncio
    async def test_mixed_evidence_candidate_survives_with_risk_item_stripped(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A candidate with both risk and non-risk evidence must survive in
        the artifact, but with the risk-lexicon item removed from its
        evidence list — not merely flagged."""
        risk_quote = "살고 싶지 않아요. 매일 밤 그 생각만 들어요."
        clean_quote = "요즘 잠을 잘 못 자고 계속 불안해요."
        conv_path = self._conversation(
            tmp_path,
            turns=[
                {"turn": 0, "patient_message": risk_quote, "agent_response": "안녕"},
                {"turn": 1, "patient_message": clean_quote, "agent_response": "그렇군요"},
            ],
        )

        class _StubAgent:
            def __init__(self, model_router: object, prompt_loader: object) -> None:
                pass

            async def run(self, inp: object) -> DomainInferenceOutput:
                return DomainInferenceOutput(
                    model_used="stub", prompt_version="v1", latency_ms=5.0,
                    reason_summary="stub",
                    domain_candidates=[
                        DomainCandidate(
                            domain="depression", confidence=0.6,
                            evidence=[
                                DomainEvidence(
                                    source_type="utterance", source_id="turn_0", quote=risk_quote
                                ),
                                DomainEvidence(
                                    source_type="utterance", source_id="turn_1", quote=clean_quote
                                ),
                            ],
                        )
                    ],
                    department_candidates=[],
                    summary="우울 호소",
                    retrieval_meta=RetrievalMeta(mode="llm_only", chunks_returned=0, chunk_ids=[]),
                )

        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(self._run_args(conv_path, out_dir))

        json_files = list((out_dir / "VP-CASCADE").glob("*_domain_inference.json"))
        report_files = list((out_dir / "VP-CASCADE").glob("*_report.md"))
        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))

        assert len(artifact["domain_candidates"]) == 1
        cand = artifact["domain_candidates"][0]
        assert cand["domain"] == "depression"
        # Only the clean, non-risk evidence item survives.
        assert len(cand["evidence"]) == 1
        assert cand["evidence"][0]["source_id"] == "turn_1"
        assert all(risk_quote not in ev["quote"] for ev in cand["evidence"])

        fs = artifact["filter_summary"]
        assert fs["candidates_before"] == 1
        assert fs["candidates_after"] == 1
        assert fs["candidates_eliminated"] == 0
        assert fs["eliminated_domains"] == []
        assert fs["evidence_stripped"] == 1
        assert fs["evidence_stripped_risk_lexicon"] == 1
        assert artifact["whitelist_audit"]["counts"]["rejected_risk_lexicon"] == 1

        report = report_files[0].read_text(encoding="utf-8")
        assert "STRIPPED" in report

    @pytest.mark.asyncio
    async def test_department_referencing_cascade_eliminated_domain_is_orphan(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """QA gate 1g (PLAN-2026-W28-E) adjudication of the developer's
        post-cascade orphan-check wiring (`f2.py::_run`, `find_orphan_departments
        (filtered_candidates, ...)` not `output.domain_candidates`): a
        department_candidate whose domain_ref points to a domain the cascade
        eliminated (all evidence rejected as risk-lexicon) must be flagged as
        an orphan in the live artifact, even though it was NOT an orphan in
        the LLM's raw pre-cascade output.

        This closes a real gap: checking orphan status against the raw
        pre-cascade domain list would silently miss this case (a "masked
        orphan" -- the domain_ref pointed at something real when the LLM
        emitted it, but the artifact's actual domain_candidates no longer
        contains it after the cascade runs). Verified by QA to regress
        (reverting the wiring to `output.domain_candidates` passes the full
        671-test suite with zero failures) before this test was added.
        """
        risk_quote = "살고 싶지 않아요. 매일 밤 그 생각만 들어요."
        conv_path = self._conversation(
            tmp_path,
            turns=[{"turn": 0, "patient_message": risk_quote, "agent_response": "안녕"}],
        )

        class _StubAgent:
            def __init__(self, model_router: object, prompt_loader: object) -> None:
                pass

            async def run(self, inp: object) -> DomainInferenceOutput:
                return DomainInferenceOutput(
                    model_used="stub", prompt_version="v1", latency_ms=5.0,
                    reason_summary="stub",
                    domain_candidates=[
                        DomainCandidate(
                            domain="depression", confidence=0.6,
                            evidence=[
                                DomainEvidence(
                                    source_type="utterance", source_id="turn_0", quote=risk_quote
                                )
                            ],
                        )
                    ],
                    department_candidates=[
                        DepartmentCandidate(
                            department="정신건강의학과", domain_ref="depression",
                            reason="우울 증상 호소",
                        )
                    ],
                    summary="우울 호소",
                    retrieval_meta=RetrievalMeta(mode="llm_only", chunks_returned=0, chunk_ids=[]),
                )

        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(self._run_args(conv_path, out_dir))

        json_files = list((out_dir / "VP-CASCADE").glob("*_domain_inference.json"))
        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))

        # The "depression" domain candidate was eliminated by the cascade...
        assert artifact["domain_candidates"] == []
        assert artifact["filter_summary"]["eliminated_domains"] == ["depression"]
        # ...so the department that referenced it is now an orphan in the
        # live artifact, even though department_candidates itself is untouched
        # by the evidence cascade (department_candidates has no evidence field).
        assert len(artifact["department_candidates"]) == 1
        assert artifact["department_candidates"][0]["domain_ref"] == "depression"
        assert len(artifact["orphan_departments"]) == 1
        assert artifact["orphan_departments"][0]["department"] == "정신건강의학과"


# ── PLAN-2026-W28-K Task 3 (ADR-020/ADR-021) — Track B live population ─────


class TestExtractQuote:
    def test_centers_a_short_excerpt_on_the_matched_term(self) -> None:
        text = "환자가 " + ("가" * 60) + "불면" + ("나" * 60) + "증상을 호소함"
        quote = f2._extract_quote(text, "불면", window=10)
        assert "불면" in quote
        assert len(quote) < len(text)

    def test_no_truncation_marker_when_excerpt_covers_full_text(self) -> None:
        text = "요즘 잠을 잘 못 자요"
        quote = f2._extract_quote(text, "잠을", window=40)
        assert quote == text
        assert not quote.startswith("...")
        assert not quote.endswith("...")

    def test_truncation_markers_added_on_both_sides_when_clipped(self) -> None:
        text = ("가" * 100) + "불면" + ("나" * 100)
        quote = f2._extract_quote(text, "불면", window=10)
        assert quote.startswith("...")
        assert quote.endswith("...")
        assert "불면" in quote

    def test_defensive_fallback_when_term_not_actually_in_text(self) -> None:
        """Should not happen on the live path (the term is only ever passed
        in because it was found as a substring) — kept total for synthetic
        unit-test inputs."""
        quote = f2._extract_quote("아무 관련 없는 텍스트", "존재하지않는단어", window=10)
        assert isinstance(quote, str)


class TestClampSimilarityScore:
    def test_negative_score_clamped_to_zero(self) -> None:
        assert f2._clamp_similarity_score(-0.05) == 0.0

    def test_above_one_clamped_to_one(self) -> None:
        assert f2._clamp_similarity_score(1.2) == 1.0

    def test_in_range_score_unchanged(self) -> None:
        assert f2._clamp_similarity_score(0.734) == 0.734

    def test_boundary_values_unchanged(self) -> None:
        assert f2._clamp_similarity_score(0.0) == 0.0
        assert f2._clamp_similarity_score(1.0) == 1.0


class TestAggregateDiseaseCandidates:
    """Pure, DB-free correctness tests for RES-001 §2 steps 4-9 / ADR-020
    conditions 1/2/4 — no async, no DB, no live LLM."""

    def test_candidate_carries_correct_provenance(self) -> None:
        chunk = {
            "chunk_id": "case_card:42", "text": "환자가 불안하고 잠을 잘 못 잔다고 호소함",
            "score": 0.75,
        }
        candidates, n_dropped = f2._aggregate_disease_candidates(
            [(chunk, "불안장애", "불안")]
        )
        assert n_dropped == 0
        assert len(candidates) == 1
        c = candidates[0]
        assert c.disease == "불안장애"
        assert c.similarity_score == 0.75
        assert c.source_id == "case_card:42"
        assert c.quote is not None
        assert "불안" in c.quote

    def test_max_not_sum_aggregation_across_chunks(self) -> None:
        """A disease mentioned in multiple chunks keeps the single highest
        score — never a sum/average of the two (ADR-020 condition to avoid
        a softmax-adjacent drift, REV-013 §4(b))."""
        low_chunk = {"chunk_id": "qa:1", "text": "우울한 기분이 든다고 함", "score": 0.4}
        high_chunk = {"chunk_id": "case_card:9", "text": "심한 우울감을 호소함", "score": 0.9}
        votes = [
            (low_chunk, "우울장애", "우울"),
            (high_chunk, "우울장애", "우울"),
        ]
        candidates, n_dropped = f2._aggregate_disease_candidates(votes)
        assert n_dropped == 0
        assert len(candidates) == 1
        c = candidates[0]
        assert c.similarity_score == 0.9
        assert c.source_id == "case_card:9"  # the WINNING chunk's provenance
        assert c.similarity_score != 0.4 + 0.9  # not the sum of both votes' scores

    def test_top_5_cap_no_padding_when_more_than_5(self) -> None:
        votes = [
            (
                {"chunk_id": f"qa:{i}", "text": f"증상{i} 관련 내용", "score": 0.1 * i},
                f"disease{i}", f"증상{i}",
            )
            for i in range(1, 8)  # 7 distinct diseases
        ]
        candidates, _ = f2._aggregate_disease_candidates(votes)
        assert len(candidates) == 5
        scores = [c.similarity_score for c in candidates]
        assert scores == sorted(scores, reverse=True)

    def test_no_padding_when_fewer_than_5(self) -> None:
        votes = [
            ({"chunk_id": "qa:1", "text": "불안 증상 호소", "score": 0.5}, "불안장애", "불안"),
        ]
        candidates, _ = f2._aggregate_disease_candidates(votes)
        assert len(candidates) == 1  # not padded to 5

    def test_legitimate_zero_candidate_outcome(self) -> None:
        candidates, n_dropped = f2._aggregate_disease_candidates([])
        assert candidates == []
        assert n_dropped == 0

    def test_risk_lexicon_flagged_quote_is_dropped_not_shipped(self) -> None:
        """VAL-011/ADR-020 condition 1 (blocking-scoped) — a vote whose
        extracted quote contains a risk-class phrase must be dropped
        entirely (never clipped/redacted, never shipped)."""
        risky_chunk = {
            "chunk_id": "qa:1685",
            "text": "요즘 살고 싶지 않다는 생각이 들고 잠을 잘 못 자요.",
            "score": 0.88,
        }
        votes = [(risky_chunk, "우울장애", "잠을")]
        candidates, n_dropped = f2._aggregate_disease_candidates(votes)
        assert candidates == []
        assert n_dropped == 1

    def test_risk_lexicon_drop_does_not_eliminate_a_clean_sibling_vote(self) -> None:
        risky_chunk = {
            "chunk_id": "qa:1685",
            "text": "요즘 살고 싶지 않다는 생각이 들어요.",
            "score": 0.88,
        }
        clean_chunk = {
            "chunk_id": "case_card:3",
            "text": "환자가 불안 증상을 호소함",
            "score": 0.6,
        }
        votes = [
            (risky_chunk, "우울장애", "살고"),
            (clean_chunk, "불안장애", "불안"),
        ]
        candidates, n_dropped = f2._aggregate_disease_candidates(votes)
        assert n_dropped == 1
        assert len(candidates) == 1
        assert candidates[0].disease == "불안장애"

    def test_negative_score_clamped_not_crashing(self) -> None:
        """ADR-020 condition 4 / REV-016 issue #4 — a negative chunk score
        must not raise an uncaught ValidationError during aggregation."""
        chunk = {"chunk_id": "qa:1", "text": "불안 증상 호소", "score": -0.02}
        candidates, _ = f2._aggregate_disease_candidates([(chunk, "불안장애", "불안")])
        assert len(candidates) == 1
        assert candidates[0].similarity_score == 0.0

    def test_missing_score_defaults_to_zero_not_crashing(self) -> None:
        chunk = {"chunk_id": "qa:1", "text": "불안 증상 호소"}  # no "score" key
        candidates, _ = f2._aggregate_disease_candidates([(chunk, "불안장애", "불안")])
        assert len(candidates) == 1
        assert candidates[0].similarity_score == 0.0


class TestCollectChunkDiseaseVotes:
    @pytest.mark.asyncio
    async def test_collects_votes_across_chunks_skips_blank_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_match = AsyncMock(
            side_effect=[
                [("불안장애", 2, "불안")],
                [],  # second chunk (blank text) never actually reaches the mock
            ]
        )
        monkeypatch.setattr("src.rag.retrieval.match_diseases_for_chunk_text", mock_match)

        chunks = [
            {"chunk_id": "case_card:1", "text": "환자가 불안 증상을 호소함", "score": 0.6},
            {"chunk_id": "qa:2", "text": "   ", "score": 0.5},  # blank -> skipped
        ]
        votes = await f2._collect_chunk_disease_votes(object(), chunks)

        assert len(votes) == 1
        assert votes[0][0]["chunk_id"] == "case_card:1"
        assert votes[0][1] == "불안장애"
        assert votes[0][2] == "불안"
        mock_match.assert_awaited_once()


class TestBuildAiPredictedDiseasePopulated:
    @pytest.mark.asyncio
    async def test_populated_mode_rag_live_with_provenance_and_proxy_caveat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = [
            {
                "chunk_id": "case_card:1", "source_type": "case_card",
                "text": "환자가 불면과 불안을 호소함", "score": 0.82,
            }
        ]
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(return_value=[("불안장애", 2, "불안")]),
        )

        out = await f2._build_ai_predicted_disease_populated(object(), chunks)

        assert out.mode == "rag_live"
        assert len(out.candidates) == 1
        c = out.candidates[0]
        assert c.disease == "불안장애"
        assert c.similarity_score == 0.82
        assert c.source_id == "case_card:1"
        assert c.quote is not None
        assert "불안" in c.quote
        assert "NOT a patient-to-disease" in out.reason_summary
        assert "NOT a calibrated probability" in out.reason_summary
        assert out.is_diagnostic is False

    @pytest.mark.asyncio
    async def test_legitimate_zero_candidate_when_no_symptom_keyword_matched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = [
            {"chunk_id": "qa:9", "source_type": "qa", "text": "일반적인 상담 내용", "score": 0.5}
        ]
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text", AsyncMock(return_value=[])
        )

        out = await f2._build_ai_predicted_disease_populated(object(), chunks)

        assert out.mode == "rag_live"
        assert out.candidates == []
        assert "legitimate" in out.reason_summary
        assert "not an error" in out.reason_summary

    @pytest.mark.asyncio
    async def test_reason_summary_discloses_risk_lexicon_drop_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = [
            {
                "chunk_id": "qa:1685", "source_type": "qa",
                "text": "요즘 살고 싶지 않다는 생각이 들어요.", "score": 0.9,
            }
        ]
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(return_value=[("우울장애", 1, "살고")]),
        )

        out = await f2._build_ai_predicted_disease_populated(object(), chunks)

        assert out.candidates == []
        assert "risk-lexicon filter" in out.reason_summary
        assert "1 candidate vote(s)" in out.reason_summary

    @pytest.mark.asyncio
    async def test_recommendation_caveat_populated_for_real_mood_top_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CVR-003 Findings 1/3 (W5 addendum): recommendation_caveat is
        derived from the SAME top-ranked candidate's disease name as
        recommended_questionnaire, via the same
        src.rag.questionnaire_mapping module. Uses a real ontology disease
        name ("우울 삽화(우울증)", mood classification) so both fields
        resolve to real, non-None values."""
        chunks = [
            {
                "chunk_id": "case_card:1", "source_type": "case_card",
                "text": "환자가 2주 이상 지속된 우울감을 호소함", "score": 0.9,
            }
        ]
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(return_value=[("우울 삽화(우울증)", 1, "우울감")]),
        )

        out = await f2._build_ai_predicted_disease_populated(object(), chunks)

        assert out.recommended_questionnaire == "PHQ-9"
        assert out.recommendation_caveat is not None
        assert "manic" in out.recommendation_caveat or "mania" in out.recommendation_caveat.lower()

    @pytest.mark.asyncio
    async def test_recommendation_caveat_none_when_top_candidate_has_no_disclosed_caveat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real ontology disease name whose classification (anxiety) DOES
        map to a scale but has no disclosed caveat -- recommended_
        questionnaire is set, recommendation_caveat stays None."""
        chunks = [
            {
                "chunk_id": "case_card:2", "source_type": "case_card",
                "text": "환자가 만성적인 불안과 걱정을 호소함", "score": 0.9,
            }
        ]
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(return_value=[("범불안장애", 1, "불안")]),
        )

        out = await f2._build_ai_predicted_disease_populated(object(), chunks)

        assert out.recommended_questionnaire == "GAD-7"
        assert out.recommendation_caveat is None

    @pytest.mark.asyncio
    async def test_recommendation_caveat_none_when_zero_candidates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text", AsyncMock(return_value=[])
        )
        chunks = [{"chunk_id": "qa:9", "source_type": "qa", "text": "일반 상담", "score": 0.5}]

        out = await f2._build_ai_predicted_disease_populated(object(), chunks)

        assert out.candidates == []
        assert out.recommended_questionnaire is None
        assert out.recommendation_caveat is None


class TestBuildEvidenceProvenanceSummary:
    """Enhancement #4 code-side half (ADR-021, REV-016(a))."""

    def test_counts_split_by_db_table_origin_and_utterance(self) -> None:
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.5,
                evidence=[
                    DomainEvidence(
                        source_type="rag_chunk", source_id="case_card:1", quote="q1"
                    ),
                    DomainEvidence(source_type="rag_chunk", source_id="qa:2", quote="q2"),
                    DomainEvidence(source_type="rag_chunk", source_id="qa:3", quote="q3"),
                    DomainEvidence(source_type="utterance", source_id="turn_0", quote="q4"),
                ],
            ),
        ]
        summary = f2._build_evidence_provenance_summary(candidates)
        assert summary == {
            "rag_chunk_case_card": 1, "rag_chunk_qa": 2, "rag_chunk_other": 0, "utterance": 1,
            "ocr_document": 0,
        }

    def test_empty_candidates_all_zero(self) -> None:
        assert f2._build_evidence_provenance_summary([]) == {
            "rag_chunk_case_card": 0, "rag_chunk_qa": 0, "rag_chunk_other": 0, "utterance": 0,
            "ocr_document": 0,
        }

    def test_unrecognized_prefix_falls_into_other_not_silently_dropped(self) -> None:
        candidates = [
            DomainCandidate(
                domain="sleep", confidence=0.4,
                evidence=[
                    DomainEvidence(
                        source_type="rag_chunk", source_id="ontology:99", quote="q"
                    ),
                ],
            ),
        ]
        summary = f2._build_evidence_provenance_summary(candidates)
        assert summary["rag_chunk_other"] == 1
        assert summary["rag_chunk_case_card"] == 0
        assert summary["rag_chunk_qa"] == 0

    def test_summary_flows_into_artifact_and_report(self) -> None:
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.5,
                evidence=[
                    DomainEvidence(
                        source_type="rag_chunk", source_id="case_card:1", quote="근거"
                    ),
                ],
            ),
        ]
        output = DomainInferenceOutput(
            model_used="test-model", prompt_version="v1", latency_ms=1.0,
            reason_summary="stub", domain_candidates=candidates, department_candidates=[],
            summary="s",
            retrieval_meta=RetrievalMeta(
                mode="rag", chunks_returned=1, chunk_ids=["case_card:1"]
            ),
        )
        filter_summary = f2._build_filter_summary(
            candidates_before=candidates, candidates_after=candidates, counts={"accepted": 1}
        )
        artifact = f2._build_artifact(
            output=output, domain_candidates=candidates, repro={
                "git_head": "x", "model_used": "m", "prompt_version": "v1",
                "input_file": "x.json", "input_sha256": "y", "mode": "rag",
                "latency_ms": 1.0, "generated_at": "now",
            },
            chunk_texts={"case_card:1": "근거 텍스트"}, utterances={}, verdicts=[],
            counts={"accepted": 1}, filter_summary=filter_summary, orphans=[],
            session_id="t", persona_id="VP-TEST",
            evidence_provenance_summary=f2._build_evidence_provenance_summary(candidates),
        )
        assert artifact["evidence_provenance_summary"] == {
            "rag_chunk_case_card": 1, "rag_chunk_qa": 0, "rag_chunk_other": 0, "utterance": 0,
            "ocr_document": 0,
        }
        report = f2._build_report(artifact)
        assert "Evidence provenance (enhancement #4)" in report
        assert "rag_chunk(case_card): 1" in report


class TestRunWiresPopulation:
    """End-to-end (`f2._run`) wiring — mock-based, no live LLM/DB, per this
    file's own C-4 convention."""

    @staticmethod
    def _conversation(tmp_path, *, final_slots: list[dict]) -> Path:
        conversation = {
            "session_id": "f2_track_b", "persona_id": "VP-TRACKB", "persona_name": "테스트",
            "final_slots": final_slots, "session_ctrs": 5, "crisis_triggered": False,
            "crisis_turn": None, "turns": [], "probe_events": [],
        }
        conv_path = Path(tmp_path) / "VP-TRACKB_20260709_000000_conversation.json"
        conv_path.write_text(json.dumps(conversation, ensure_ascii=False), encoding="utf-8")
        return conv_path

    @pytest.mark.asyncio
    async def test_llm_only_mode_stays_experimental_unpopulated(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = self._conversation(
            tmp_path, final_slots=[{"key": "chief_complaint", "value": "불안감"}]
        )

        class _StubAgent:
            def __init__(self, model_router: object, prompt_loader: object) -> None:
                pass

            async def run(self, inp: object) -> DomainInferenceOutput:
                return DomainInferenceOutput(
                    model_used="stub", prompt_version="v1", latency_ms=1.0,
                    reason_summary="stub", domain_candidates=[], department_candidates=[],
                    summary="", retrieval_meta=RetrievalMeta(
                        mode="llm_only", chunks_returned=0, chunk_ids=[]
                    ),
                )

        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            conversation=str(conv_path), persona=None, no_rag=True, k=3,
            out=str(out_dir), scale_scores=None, first_visit=False, revisit=False,
        )
        await f2._run(args)

        json_files = list((out_dir / "VP-TRACKB").glob("*_domain_inference.json"))
        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert artifact["ai_predicted_disease"]["mode"] == "experimental_unpopulated"
        assert artifact["ai_predicted_disease"]["candidates"] == []

    @pytest.mark.asyncio
    async def test_rag_mode_populates_candidates_with_provenance_end_to_end(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = self._conversation(
            tmp_path,
            final_slots=[
                {"key": "chief_complaint", "value": "불안감과 수면 문제"},
                {"key": "history_of_present_illness", "value": "2주 전부터 악화"},
            ],
        )

        class _FakeSession:
            async def __aenter__(self) -> _FakeSession:
                return self

            async def __aexit__(self, *exc: object) -> bool:
                return False

        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        monkeypatch.setattr(
            "src.rag.retrieval.retrieve_domain_chunks",
            AsyncMock(return_value=[
                {
                    "chunk_id": "case_card:5", "source_type": "case_card",
                    "text": "환자가 불안하고 잠을 설친다고 호소", "score": 0.77,
                }
            ]),
        )
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(return_value=[("불안장애", 2, "불안")]),
        )

        class _StubAgent:
            def __init__(self, model_router: object, prompt_loader: object) -> None:
                pass

            async def run(self, inp: object) -> DomainInferenceOutput:
                return DomainInferenceOutput(
                    model_used="stub", prompt_version="v1", latency_ms=1.0,
                    reason_summary="stub", domain_candidates=[], department_candidates=[],
                    summary="", retrieval_meta=RetrievalMeta(
                        mode="rag", chunks_returned=1, chunk_ids=["case_card:5"]
                    ),
                )

        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            conversation=str(conv_path), persona=None, no_rag=False, k=3,
            out=str(out_dir), scale_scores=None, first_visit=False, revisit=False,
        )
        await f2._run(args)

        json_files = list((out_dir / "VP-TRACKB").glob("*_domain_inference.json"))
        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))
        ai_disease = artifact["ai_predicted_disease"]
        assert ai_disease["mode"] == "rag_live"
        assert len(ai_disease["candidates"]) == 1
        c = ai_disease["candidates"][0]
        assert c["disease"] == "불안장애"
        assert c["similarity_score"] == 0.77
        assert c["source_id"] == "case_card:5"
        assert "불안" in c["quote"]

    @pytest.mark.asyncio
    async def test_rag_mode_population_db_failure_degrades_not_crashes(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Population failure (e.g. a transient DB error on the SECOND
        session, opened after Stage 1's own session already closed cleanly)
        must not crash the whole F2 run — domain_candidates is unaffected,
        the AI-disease container degrades to experimental_unpopulated with
        an honest reason."""
        conv_path = self._conversation(
            tmp_path, final_slots=[{"key": "chief_complaint", "value": "불안감과 수면 문제"}]
        )

        class _FakeSession:
            async def __aenter__(self) -> _FakeSession:
                return self

            async def __aexit__(self, *exc: object) -> bool:
                return False

        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        monkeypatch.setattr(
            "src.rag.retrieval.retrieve_domain_chunks",
            AsyncMock(return_value=[
                {
                    "chunk_id": "case_card:5", "source_type": "case_card",
                    "text": "환자가 불안 증상을 호소", "score": 0.7,
                }
            ]),
        )
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(side_effect=RuntimeError("DB connection lost")),
        )

        class _StubAgent:
            def __init__(self, model_router: object, prompt_loader: object) -> None:
                pass

            async def run(self, inp: object) -> DomainInferenceOutput:
                return DomainInferenceOutput(
                    model_used="stub", prompt_version="v1", latency_ms=1.0,
                    reason_summary="stub", domain_candidates=[], department_candidates=[],
                    summary="", retrieval_meta=RetrievalMeta(
                        mode="rag", chunks_returned=1, chunk_ids=["case_card:5"]
                    ),
                )

        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            conversation=str(conv_path), persona=None, no_rag=False, k=3,
            out=str(out_dir), scale_scores=None, first_visit=False, revisit=False,
        )
        await f2._run(args)  # must not raise

        json_files = list((out_dir / "VP-TRACKB").glob("*_domain_inference.json"))
        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert artifact["ai_predicted_disease"]["mode"] == "experimental_unpopulated"
        assert artifact["ai_predicted_disease"]["candidates"] == []
