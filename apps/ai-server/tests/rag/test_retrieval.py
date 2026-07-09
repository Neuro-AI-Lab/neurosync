"""src.rag.retrieval — SQL-shape/params + decrypt-failure fallback (S2, S3).

Mock-based only: no real DB (AsyncMock stands in for AsyncSession) and no
real embedding network call (embed_query is monkeypatched — a genuine
UPSTAGE_API_KEY is present in this repo's .env, so leaving it unpatched
would attempt a live network call from an offline test).
"""

from __future__ import annotations

import base64
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.sql.elements import TextClause

from src.rag import crypto
from src.rag.retrieval import (
    _dec,
    _detect_symptoms,
    _detect_symptoms_with_term,
    _topk,
    match_diseases_for_chunk_text,
    retrieve_domain_chunks,
)


def _make_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


class TestTopkSqlShape:
    @pytest.mark.asyncio
    async def test_builds_expected_sql_text_and_params(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result)

        await _topk(
            db, "case_card", "card_id, class, situation", {"q": "[0.1,0.2]"}, 5,
            where="AND patient_id = :pid",
        )

        assert db.execute.await_count == 1
        sql_arg, params_arg = db.execute.await_args.args
        assert isinstance(sql_arg, TextClause)
        sql_text = str(sql_arg)
        assert "FROM rag.case_card" in sql_text
        assert "card_id, class, situation" in sql_text
        assert "WHERE embedding IS NOT NULL AND patient_id = :pid" in sql_text
        assert "ORDER BY embedding <=> CAST(:q AS vector)" in sql_text
        assert "LIMIT :k" in sql_text
        assert params_arg == {"q": "[0.1,0.2]", "k": 5}

    @pytest.mark.asyncio
    async def test_default_where_clause_is_empty(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result)

        await _topk(db, "qa", "qa_id, question, answer", {"q": "[0.0]"}, 3)

        sql_text = str(db.execute.await_args.args[0])
        assert "WHERE embedding IS NOT NULL" in sql_text
        assert "AND " not in sql_text.split("WHERE embedding IS NOT NULL")[1].split(
            "ORDER BY"
        )[0]


class TestRetrieveDomainChunksSqlShape:
    @pytest.mark.asyncio
    async def test_queries_case_card_and_qa_with_id_columns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.rag.retrieval.embed_query", lambda text: [0.0] * 8)

        db = AsyncMock()
        case_result = MagicMock()
        case_result.fetchall.return_value = [(1, "anxiety", "불안 사례", 0.9)]
        qa_result = MagicMock()
        qa_result.fetchall.return_value = [(2, "psychiatry", "질문", "답변", 0.8)]
        db.execute = AsyncMock(side_effect=[case_result, qa_result])

        chunks = await retrieve_domain_chunks(db, ["불안감과 수면 문제"], k=3)

        assert db.execute.await_count == 2
        first_sql = str(db.execute.await_args_list[0].args[0])
        assert "card_id, class, situation" in first_sql
        assert "FROM rag.case_card" in first_sql
        second_sql = str(db.execute.await_args_list[1].args[0])
        assert "qa_id, specialty, question, answer" in second_sql
        assert "FROM rag.qa" in second_sql

        assert chunks[0]["chunk_id"] == "case_card:1"
        assert chunks[0]["text"] == "불안 사례"
        assert chunks[1]["chunk_id"] == "qa:2"
        assert "Q: 질문" in chunks[1]["text"] and "A: 답변" in chunks[1]["text"]

    @pytest.mark.asyncio
    async def test_skips_blank_queries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.rag.retrieval.embed_query", lambda text: [0.0] * 8)
        db = AsyncMock()
        db.execute = AsyncMock()

        chunks = await retrieve_domain_chunks(db, ["", "   "], k=3)

        assert chunks == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedupes_repeated_chunk_ids_across_queries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.rag.retrieval.embed_query", lambda text: [0.0] * 8)
        db = AsyncMock()
        same_case = MagicMock()
        same_case.fetchall.return_value = [(1, "anxiety", "불안 사례", 0.9)]
        empty_qa = MagicMock()
        empty_qa.fetchall.return_value = []
        # Two queries, each producing the identical case_card:1 row.
        db.execute = AsyncMock(
            side_effect=[same_case, empty_qa, same_case, empty_qa]
        )

        chunks = await retrieve_domain_chunks(db, ["q1", "q2"], k=3)

        assert len(chunks) == 1
        assert chunks[0]["chunk_id"] == "case_card:1"


class TestDetectSymptomsWithTerm:
    """F2 Track B (PLAN-2026-W28-K, RES-001 §2 step 2) — the matched-term
    variant `_detect_symptoms` now wraps, plus `_detect_symptoms` itself
    stays behavior-compatible (returns only (id, name) tuples)."""

    _SYMPTOM_ROWS = [
        (1, "insomnia", "불면", ["잠을 잘 못 자", "수면 문제"]),
        (2, "anxiety", "불안", []),
    ]

    @pytest.mark.asyncio
    async def test_returns_matched_term_alongside_symptom_id_and_name(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = self._SYMPTOM_ROWS
        db.execute = AsyncMock(return_value=result)

        hits = await _detect_symptoms_with_term(db, "요즘 잠을 잘 못 자고 불안해요.")

        assert (1, "불면", "잠을 잘 못 자") in hits
        assert (2, "불안", "불안") in hits
        assert len(hits) == 2

    @pytest.mark.asyncio
    async def test_synonym_match_returns_the_synonym_as_matched_term(self) -> None:
        """A synonym match (not the canonical name_ko) still returns the
        LITERAL matched substring, not the canonical name — needed to build
        a genuinely verbatim quote excerpt (RES-001 §2 step 8)."""
        db = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = self._SYMPTOM_ROWS
        db.execute = AsyncMock(return_value=result)

        hits = await _detect_symptoms_with_term(db, "요즘 수면 문제가 있어요.")

        assert hits == [(1, "불면", "수면 문제")]

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = self._SYMPTOM_ROWS
        db.execute = AsyncMock(return_value=result)

        assert await _detect_symptoms_with_term(db, "아무 증상도 언급 없음") == []

    @pytest.mark.asyncio
    async def test_detect_symptoms_still_returns_only_id_and_name(self) -> None:
        """`_detect_symptoms` (used by `retrieve_grounding`'s live-chat path)
        must be unaffected in shape by this refactor — 2-tuples, no term."""
        db = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = self._SYMPTOM_ROWS
        db.execute = AsyncMock(return_value=result)

        hits = await _detect_symptoms(db, "요즘 잠을 잘 못 자고 불안해요.")

        assert hits == [(1, "불면"), (2, "불안")]


class TestMatchDiseasesForChunkText:
    """F2 Track B (PLAN-2026-W28-K, RES-001 §2 step 3, ADR-020 path1)."""

    @pytest.mark.asyncio
    async def test_no_symptom_match_returns_empty_without_a_second_query(self) -> None:
        db = AsyncMock()
        symptom_result = MagicMock()
        symptom_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=symptom_result)

        votes = await match_diseases_for_chunk_text(db, "일반적인 상담 내용입니다.")

        assert votes == []
        # Only the rag.symptom lookup ran — no disease_symptom JOIN attempted.
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_widened_limit_can_return_more_than_one_disease(self) -> None:
        db = AsyncMock()
        symptom_result = MagicMock()
        symptom_result.fetchall.return_value = [(1, "insomnia", "불면", [])]
        disease_result = MagicMock()
        disease_result.fetchall.return_value = [("우울장애", 3), ("불안장애", 1)]
        db.execute = AsyncMock(side_effect=[symptom_result, disease_result])

        votes = await match_diseases_for_chunk_text(db, "요즘 불면 증상이 있어요.", limit=2)

        assert votes == [("우울장애", 3, "불면"), ("불안장애", 1, "불면")]
        disease_sql = str(db.execute.await_args_list[1].args[0])
        assert "LIMIT :limit" in disease_sql
        assert db.execute.await_args_list[1].args[1]["limit"] == 2

    @pytest.mark.asyncio
    async def test_matched_term_is_the_literal_substring_not_the_canonical_name(self) -> None:
        db = AsyncMock()
        symptom_result = MagicMock()
        symptom_result.fetchall.return_value = [(1, "insomnia", "불면", ["잠을 설쳐"])]
        disease_result = MagicMock()
        disease_result.fetchall.return_value = [("우울장애", 1)]
        db.execute = AsyncMock(side_effect=[symptom_result, disease_result])

        votes = await match_diseases_for_chunk_text(db, "요즘 잠을 설쳐서 힘들어요.")

        assert votes == [("우울장애", 1, "잠을 설쳐")]


class TestDecFailureFallback:
    """S2: decrypt failure/absent key -> field excluded (None), not a crash,
    not a garbled utf-8 decode of ciphertext bytes (the pre-fix behaviour)."""

    def test_none_input_returns_none(self) -> None:
        assert _dec(None) is None

    def test_missing_key_returns_none_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        assert _dec(b"x" * 20) is None

    def test_malformed_ciphertext_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        assert _dec(os.urandom(30)) is None  # not valid AESGCM output for this key

    def test_valid_ciphertext_decrypts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        aad = crypto.session_insights_aad("sess-9", "situation")
        blob = crypto.encrypt_str("불안감과 수면 문제", aad=aad)
        assert _dec(blob, aad=aad) == "불안감과 수면 문제"

    def test_wrong_aad_returns_none_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY", _make_key())
        blob = crypto.encrypt_str("불안감과 수면 문제", aad=b"aad-a")
        assert _dec(blob, aad=b"aad-b") is None
