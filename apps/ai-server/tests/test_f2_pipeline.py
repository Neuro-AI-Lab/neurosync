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
