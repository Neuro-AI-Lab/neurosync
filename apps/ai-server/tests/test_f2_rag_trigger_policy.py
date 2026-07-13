"""`src.f2` — RAG trigger Policy A/B integration (PLAN-2026-W28-Q W4).

Pipeline-level (`f2._run`/`f2.main`), mock-based only — no live LLM/DB
anywhere in this file, mirroring `test_f2_pipeline.py`'s own C-4 convention.
Covers: config-driven arm switch (default A), single-choke-point filter
applied end-to-end through `run_stage1`, `rag_trigger` artifact persistence
(incl. Policy-B judge I/O), and the MET-6 mode-consistency triple
(`rag_trigger.retrieve` / `repro.mode` / `ai_predicted_disease.mode`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.f2 as f2
from src.schemas.domain_inference import DomainInferenceOutput, RetrievalMeta


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _StubDomainAgent:
    def __init__(self, model_router: object, prompt_loader: object) -> None:
        pass

    async def run(self, inp: object) -> DomainInferenceOutput:
        return DomainInferenceOutput(
            model_used="stub", prompt_version="v1", latency_ms=1.0,
            reason_summary="stub", domain_candidates=[], department_candidates=[],
            summary="", retrieval_meta=RetrievalMeta(
                mode=getattr(inp, "retrieval_mode", "llm_only"),
                chunks_returned=len(getattr(inp, "retrieved_chunks", []) or []),
                chunk_ids=[c.chunk_id for c in (getattr(inp, "retrieved_chunks", []) or [])],
            ),
        )


class _StubJudgeAgent:
    """Mirrors `DomainInferenceAgent`'s constructor shape (`(model_router,
    prompt_loader)`) so it drops in as `f2.RagTriggerJudgeAgent`."""

    def __init__(self, retrieve: bool, query: str | None) -> None:
        self._retrieve = retrieve
        self._query = query
        self.received_input = None

    def __call__(self, model_router: object, prompt_loader: object) -> _StubJudgeAgent:
        return self

    async def run(self, inp: object):
        from src.schemas.rag_trigger_judge import RagTriggerJudgeOutput

        self.received_input = inp
        return RagTriggerJudgeOutput(
            model_used="stub-judge", prompt_version="v1", latency_ms=1.0,
            reason_summary="stub judge decision",
            retrieve=self._retrieve, query=self._query,
        )


def _conversation(tmp_path: Path, *, final_slots: list[dict], turns: list[dict],
                   probe_events: list[dict] | None = None) -> Path:
    conversation = {
        "session_id": "f2_rag_trigger", "persona_id": "VP-TRIGGER", "persona_name": "테스트",
        "final_slots": final_slots, "session_ctrs": 5, "crisis_triggered": False,
        "crisis_turn": None, "turns": turns, "probe_events": probe_events or [],
    }
    conv_path = Path(tmp_path) / "VP-TRIGGER_20260711_000000_conversation.json"
    conv_path.write_text(json.dumps(conversation, ensure_ascii=False), encoding="utf-8")
    return conv_path


def _args(conv_path: Path, out_dir: Path, *, no_rag: bool = False, policy: str = "A",
          include_policy_field: bool = True) -> argparse.Namespace:
    fields = dict(
        conversation=str(conv_path), persona=None, no_rag=no_rag, k=3,
        out=str(out_dir), scale_scores=None, first_visit=False, revisit=False,
    )
    if include_policy_field:
        fields["rag_trigger_policy"] = policy
    return argparse.Namespace(**fields)


def _read_artifact(out_dir: Path) -> dict:
    json_files = list((out_dir / "VP-TRIGGER").glob("*_domain_inference.json"))
    assert len(json_files) == 1
    return json.loads(json_files[0].read_text(encoding="utf-8"))


class TestConfigDrivenArmSwitch:
    def test_cli_parser_default_policy_is_a(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, str] = {}

        async def fake_run(args: argparse.Namespace) -> None:
            captured["policy"] = args.rag_trigger_policy

        monkeypatch.setattr(f2, "_run", fake_run)
        monkeypatch.setattr(
            sys, "argv", ["f2.py", "--conversation", "dummy.json", "--no-rag"]
        )
        f2.main()
        assert captured["policy"] == "A"

    def test_cli_parser_accepts_policy_b(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, str] = {}

        async def fake_run(args: argparse.Namespace) -> None:
            captured["policy"] = args.rag_trigger_policy

        monkeypatch.setattr(f2, "_run", fake_run)
        monkeypatch.setattr(
            sys, "argv",
            ["f2.py", "--conversation", "dummy.json", "--no-rag", "--rag-trigger-policy", "B"],
        )
        f2.main()
        assert captured["policy"] == "B"

    def test_missing_policy_field_on_namespace_defaults_to_a(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Robustness for hand-built Namespaces that predate this wave
        (`src/continuous_test.py`'s own `f2._run(args)` call site) — must
        not AttributeError, must behave as Policy A."""
        conv_path = _conversation(
            tmp_path,
            final_slots=[{"key": "chief_complaint", "value": "불안감"}],
            turns=[],
        )
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        args = _args(conv_path, out_dir, no_rag=True, include_policy_field=False)
        assert not hasattr(args, "rag_trigger_policy")

        import asyncio

        asyncio.run(f2._run(args))
        artifact = _read_artifact(out_dir)
        assert artifact["rag_trigger"]["policy"] == "A"


class TestNoRagShortCircuit:
    @pytest.mark.asyncio
    async def test_no_rag_records_honest_decision_never_calls_judge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = _conversation(
            tmp_path,
            final_slots=[{"key": "chief_complaint", "value": "불안감"}],
            turns=[],
        )
        judge = _StubJudgeAgent(retrieve=True, query="should never be called")
        monkeypatch.setattr(f2, "RagTriggerJudgeAgent", judge)
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(_args(conv_path, out_dir, no_rag=True, policy="B"))

        artifact = _read_artifact(out_dir)
        assert artifact["rag_trigger"]["policy"] == "B"
        assert artifact["rag_trigger"]["retrieve"] is False
        assert artifact["rag_trigger"]["trigger_reason"] == "no_rag_flag"
        assert judge.received_input is None  # judge never invoked
        assert artifact["repro"]["mode"] == "llm_only"


class TestPolicyAEndToEnd:
    @pytest.mark.asyncio
    async def test_default_policy_a_records_trigger_and_retrieves(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = _conversation(
            tmp_path,
            final_slots=[
                {"key": "chief_complaint", "value": "불안감과 수면 문제가 지속되고 있음"},
                {"key": "history_of_present_illness", "value": "2주 전부터 점진적으로 악화됨"},
            ],
            turns=[],
        )
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        mock_retrieve = AsyncMock(return_value=[])
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(_args(conv_path, out_dir, policy="A"))

        artifact = _read_artifact(out_dir)
        rt = artifact["rag_trigger"]
        assert rt["policy"] == "A"
        assert rt["retrieve"] is True
        assert rt["fallback_used"] is False
        assert artifact["repro"]["mode"] == "rag"
        # MET-6 mode-consistency triple.
        assert rt["retrieve"] is True and artifact["repro"]["mode"] == "rag"

    @pytest.mark.asyncio
    async def test_choke_point_strips_risky_cc_before_it_reaches_stage1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end proof (not just the unit-level `src.rag_trigger`
        tests): a risk-lexicon-flagged chief_complaint never reaches
        `retrieve_domain_chunks`'s query argument, even on Policy A's
        default/sufficient path (REV-022 finding 3d)."""
        risky_cc = (
            "살고 싶지 않다는 생각이 계속 들고 무기력하며 답답함을 느끼고 잠도 잘 못 이룸"
        )
        hpi = "2주 전부터 점진적으로 악화되어 일상생활에 지장이 크게 있음"
        conv_path = _conversation(
            tmp_path,
            final_slots=[
                {"key": "chief_complaint", "value": risky_cc},
                {"key": "history_of_present_illness", "value": hpi},
            ],
            turns=[],
        )
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        mock_retrieve = AsyncMock(return_value=[])
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(_args(conv_path, out_dir, policy="A"))

        mock_retrieve.assert_awaited_once()
        called_queries = mock_retrieve.call_args.args[1]
        assert risky_cc not in called_queries
        assert hpi in called_queries

        artifact = _read_artifact(out_dir)
        assert risky_cc in artifact["rag_trigger"]["dropped_queries"]

    @pytest.mark.asyncio
    async def test_vp003_run2_shape_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """data's W4 flag (Appendix A item 4), reproduced end-to-end through
        `f2._run`: a terse-but-complete (54-ish char) cc+HPI pair with a
        risk-lexicon-flagged chief_complaint routes into the fallback path
        AND the filter strips the risky content before Stage 1 ever sees
        it — asserted at the full pipeline level, not just `src.rag_
        trigger`'s pure functions."""
        risky_cc = "요즘 계속 살고 싶지 않다는 생각이 들고 무기력하고 답답함"
        hpi = "2주 전부터 악화되고 불면도 동반됨"
        assert len(risky_cc) + len(hpi) < 75

        conv_path = _conversation(
            tmp_path,
            final_slots=[
                {"key": "chief_complaint", "value": risky_cc},
                {"key": "history_of_present_illness", "value": hpi},
            ],
            turns=[
                {"turn": 0, "patient_message": risky_cc, "agent_response": "안녕"},
                {
                    "turn": 1, "patient_message": "네, 최근 잠도 잘 못 자요",
                    "agent_response": "그렇군요",
                },
            ],
            probe_events=[
                {
                    "type": "trigger", "turn": 0, "ctrs": 3, "categories": [],
                    "utterance": risky_cc,
                }
            ],
        )
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        mock_retrieve = AsyncMock(return_value=[])
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(_args(conv_path, out_dir, policy="A"))

        artifact = _read_artifact(out_dir)
        rt = artifact["rag_trigger"]
        assert rt["fallback_used"] is True
        assert risky_cc not in rt["queries"]
        assert risky_cc in rt["dropped_queries"]
        assert rt["retrieve"] is True  # the clean HPI/turn-1 query still retrieves

        mock_retrieve.assert_awaited_once()
        called_queries = mock_retrieve.call_args.args[1]
        assert risky_cc not in called_queries


class TestPolicyBEndToEnd:
    @pytest.mark.asyncio
    async def test_judge_retrieve_true_triggers_rag_and_persists_judge_io(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = _conversation(
            tmp_path, final_slots=[{"key": "chief_complaint", "value": "불안감"}], turns=[],
        )
        judge = _StubJudgeAgent(retrieve=True, query="불안감과 수면 문제")
        monkeypatch.setattr(f2, "RagTriggerJudgeAgent", judge)
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        mock_retrieve = AsyncMock(return_value=[])
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(_args(conv_path, out_dir, policy="B"))

        artifact = _read_artifact(out_dir)
        rt = artifact["rag_trigger"]
        assert rt["policy"] == "B"
        assert rt["retrieve"] is True
        assert rt["queries"] == ["불안감과 수면 문제"]
        assert rt["judge_output"]["retrieve"] is True
        assert rt["judge_output"]["query"] == "불안감과 수면 문제"
        assert artifact["repro"]["mode"] == "rag"
        # risk_assessment never reaches the judge's own input, even absent here.
        assert "risk_assessment" not in judge.received_input.final_slots

    @pytest.mark.asyncio
    async def test_judge_retrieve_false_stays_llm_only_mode_consistent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MET-6 mode-consistency triple: rag_trigger.retrieve,
        repro.mode, and ai_predicted_disease.mode must all agree when the
        judge declines to retrieve."""
        conv_path = _conversation(
            tmp_path, final_slots=[{"key": "chief_complaint", "value": "불안감"}], turns=[],
        )
        judge = _StubJudgeAgent(retrieve=False, query=None)
        monkeypatch.setattr(f2, "RagTriggerJudgeAgent", judge)
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(_args(conv_path, out_dir, policy="B"))

        artifact = _read_artifact(out_dir)
        rt = artifact["rag_trigger"]
        assert rt["retrieve"] is False
        assert artifact["repro"]["mode"] == "llm_only"
        assert artifact["ai_predicted_disease"]["mode"] == "experimental_unpopulated"

    @pytest.mark.asyncio
    async def test_judge_composed_risky_query_filtered_never_reaches_stage1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = _conversation(
            tmp_path, final_slots=[{"key": "chief_complaint", "value": "불안감"}], turns=[],
        )
        risky_query = "죽고 싶다는 생각이 계속 듦"
        judge = _StubJudgeAgent(retrieve=True, query=risky_query)
        monkeypatch.setattr(f2, "RagTriggerJudgeAgent", judge)
        monkeypatch.setattr(f2, "get_sessionmaker", lambda: (lambda: _FakeSession()))
        mock_retrieve = AsyncMock(return_value=[])
        monkeypatch.setattr("src.rag.retrieval.retrieve_domain_chunks", mock_retrieve)
        monkeypatch.setattr(f2, "DomainInferenceAgent", _StubDomainAgent)
        monkeypatch.setattr(f2, "get_model_router", lambda: None)
        monkeypatch.setattr(f2, "get_prompt_loader", lambda: None)

        out_dir = tmp_path / "out"
        await f2._run(_args(conv_path, out_dir, policy="B"))

        mock_retrieve.assert_not_awaited()
        artifact = _read_artifact(out_dir)
        rt = artifact["rag_trigger"]
        assert rt["retrieve"] is False
        assert risky_query in rt["dropped_queries"]
        # The judge's OWN raw decision is still preserved for audit.
        assert rt["judge_output"]["retrieve"] is True
        assert artifact["repro"]["mode"] == "llm_only"
