"""F2 pipeline — RAG 기반 정신건강 영역(domain)/진료과(department) 후보 추론.

PLAN-2026-W28-C (discussion.md) 검증 파이프라인, `f1.py` 패턴을 따른다:

    입력 로드 → Stage 1 검색(rag/retrieval.py 재사용, 실패 시 mode=llm_only 강등,
    ANY failure never crashes) → Stage 2 LLM(DomainInferenceAgent) →
    근거-화이트리스트 검사 + 거부 캐스케이드(src.eval.f2_grounding.
    filter_domain_candidates, 코드 레벨, REV-006 #1 / ADR-014) — 거부된 근거는
    제거되고 근거가 0개가 된 후보는 산출물에서 탈락 → 산출물(JSON + report.md,
    post-cascade domain_candidates + filter_summary + 재현 메타 포함) → 콘솔 요약.

프로덕션 통합(orchestrator.py/11-state machine) 범위 밖 — G-D 게이트로 보류
(discussion.md PLAN-2026-W28-C C-3). 이 파일은 검증 하네스일 뿐이다.

Usage:
    cd apps/ai-server
    .venv/bin/python -m src.f2 --persona VP-001
    .venv/bin/python -m src.f2 --conversation path/to/xxx_conversation.json
    .venv/bin/python -m src.f2 --persona VP-001 --no-rag
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.domain_inference import DomainInferenceAgent
from src.agents.rag_trigger_judge import RagTriggerJudgeAgent
from src.dependencies import get_model_router, get_prompt_loader, get_sessionmaker
from src.eval.f2_grounding import (
    # VAL-011/ADR-020 condition 1: the SAME risk-lexicon primitives the
    # domain_candidates cascade already uses (ADR-014), reused here so the
    # chunk-derived AI-predicted-disease population path is code-enforced by
    # the identical filter, not a re-implemented/drifting copy of it.
    _RISK_PHRASES,
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_RISK_LEXICON,
    _contains_any,
    filter_domain_candidates,
    find_orphan_departments,
)
from src.f1 import OUTPUT_DIR
from src.prompts.loader import resolve_prompts_base_dir
from src.rag.questionnaire_mapping import resolve_questionnaire_for_disease_name_ko

# PLAN-2026-W28-Q W4: RAG trigger Policy A/B — `_STAGE1_QUERY_SLOTS` now
# lives in `src.rag_trigger` (single source of truth for both this module's
# own default composition and the trigger-policy mechanism, so the two can
# never silently drift apart), re-exported here under its historical name
# for existing callers/tests (`f2._STAGE1_QUERY_SLOTS`,
# `tests/test_f2_pipeline.py`). See `src.rag_trigger`'s module docstring for
# the full VAL-010/REV-022 rationale this constant used to carry inline.
from src.rag_trigger import STAGE1_QUERY_SLOTS as _STAGE1_QUERY_SLOTS
from src.rag_trigger import decide_policy_a, decide_policy_b, no_rag_decision
from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.domain_inference import (
    DomainCandidate,
    DomainInferenceInput,
    DomainInferenceOutput,
    RetrievedChunk,
    UtteranceTurn,
)
from src.schemas.handoff import ScaleScore

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # apps/ai-server/src/f2.py → neurosync/

_REVISIT_GREETING_MARKER = "지난번 상담 기록을 확인했습니다"


# ── Input loading ────────────────────────────────────────────────────


def _find_latest_conversation(persona_id: str) -> Path | None:
    """Same glob pattern as f1.py's `_load_latest_result` (sub-dir + legacy flat)."""
    import glob as _glob

    pattern_sub = str(OUTPUT_DIR / persona_id / f"{persona_id}_*_conversation.json")
    pattern_flat = str(OUTPUT_DIR / f"{persona_id}_*_conversation.json")
    files = sorted(_glob.glob(pattern_sub) + _glob.glob(pattern_flat))
    return Path(files[-1]) if files else None


def _load_input(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    """Return (raw F1 conversation dict, source path) — never crashes silently.

    Missing/empty input is a hard exit with a clear message (no silent empty run).
    """
    if args.conversation:
        path = Path(args.conversation)
        if not path.exists():
            logger.error("f2.input.not_found — %s", path)
            print(f"Conversation file not found: {path}")
            sys.exit(1)
    else:
        found = _find_latest_conversation(args.persona)
        if found is None:
            logger.error("f2.input.no_f1_result — persona=%s", args.persona)
            print(
                f"No F1 result found for persona {args.persona} under {OUTPUT_DIR} "
                "— run f1.py first."
            )
            sys.exit(1)
        path = found

    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("final_slots") and not data.get("turns"):
        logger.warning(
            "f2.input.empty — %s has neither final_slots nor turns; proceeding with "
            "an empty clinical context (candidates will likely be empty too)",
            path,
        )
    return data, path


def _infer_is_first_visit(data: dict[str, Any]) -> bool:
    """Consume F1Result's persisted ``is_revisit`` field when present
    (PLAN-2026-W28-Q W2, REV-023 ruling 4 — binding atomicity constraint).

    Dialogue v3's autonomous turn-0 greeting (`docs/ai/prompts/dialogue/
    v3.system.md`) removed the hardcoded greeting string
    `_REVISIT_GREETING_MARKER` relied on, so that substring match can no
    longer be the primary signal — it silently stops matching, not fails
    loud. Legacy fallback (documented, for pre-W2 artifacts that lack the
    ``is_revisit`` field): substring-match F1's old hardcoded v2-era turn-0
    greeting. Overridable via --first-visit/--revisit.
    """
    if "is_revisit" in data:
        return not bool(data["is_revisit"])

    # Legacy fallback — pre-`is_revisit`-field artifacts only.
    turns = data.get("turns", [])
    if turns:
        turn0 = next((t for t in turns if t.get("turn") == 0), turns[0])
        if _REVISIT_GREETING_MARKER in (turn0.get("agent_response") or ""):
            return False
    return True


def _load_scale_scores(path_str: str | None) -> list[ScaleScore]:
    if not path_str:
        return []
    path = Path(path_str)
    if not path.exists():
        logger.warning("f2.scale_scores.not_found — %s (skipping, no F3 scores)", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [ScaleScore.model_validate(d) for d in raw]
    except Exception as exc:
        logger.warning("f2.scale_scores.invalid — %s: %s (skipping)", path, exc)
        return []


# ── Stage 1: RAG retrieval (reuse src/rag/retrieval.py primitives) ────


async def run_stage1(
    final_slots: dict[str, str],
    *,
    no_rag: bool,
    k: int,
    queries_override: list[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Returns (mode, chunks). mode is 'llm_only' on --no-rag, empty queries, or
    ANY Stage-1 failure (DB/embedding) — never raises, never crashes the run
    (REV-006 condition 6: the fallback is explicit and reported, not silent).

    Args:
        queries_override: PLAN-2026-W28-Q W4 — when given (not ``None``),
            used AS-IS instead of the default cc/HPI composition. The
            RAG-trigger-policy layer (`src.rag_trigger.decide_policy_a`/
            `decide_policy_b`, called by `_run()` below) is the only
            intended caller of this parameter — it has ALREADY applied the
            single-choke-point risk-lexicon filter (REV-022 Issues 9/10)
            to whatever it passes here. Direct callers of `run_stage1`
            that omit this argument (e.g. this module's own pre-W4 tests)
            keep the exact prior default behavior, unfiltered — matching
            `_STAGE1_QUERY_SLOTS`' own historical, still-unfiltered
            semantics for that specific call shape.
    """
    if no_rag:
        logger.info("f2.stage1.skipped — --no-rag flag set, mode=llm_only")
        return "llm_only", []

    if queries_override is not None:
        queries = queries_override
    else:
        queries = [final_slots[k2] for k2 in _STAGE1_QUERY_SLOTS if final_slots.get(k2)]
    if not queries:
        logger.warning(
            "f2.stage1.no_queries — chief_complaint/HPI (VAL-010: risk_assessment "
            "excluded from Stage-1 query slots) all empty, mode=llm_only"
        )
        return "llm_only", []

    try:
        from src.rag.retrieval import retrieve_domain_chunks

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            chunks = await retrieve_domain_chunks(db, queries, k=k)
        logger.info("f2.stage1.ok — mode=rag, chunks=%d", len(chunks))
        return "rag", chunks
    except Exception as exc:
        logger.warning(
            "f2.stage1.failed — DB/embedding error, falling back to mode=llm_only "
            "(RAG-mode run is NOT reported as such): %s", exc,
        )
        return "llm_only", []


# ── Stage 2 input assembly ─────────────────────────────────────────────


def _build_turns(data: dict[str, Any]) -> list[UtteranceTurn]:
    turns: list[UtteranceTurn] = []
    for t in data.get("turns", []):
        msg = t.get("patient_message")
        if msg:
            turns.append(UtteranceTurn(turn=t.get("turn", len(turns)), patient_message=msg))
    return turns


def _build_input(
    data: dict[str, Any],
    *,
    session_id: str,
    is_first_visit: bool,
    scale_scores: list[ScaleScore],
    mode: str,
    raw_chunks: list[dict[str, Any]],
    queries_used: list[str],
) -> DomainInferenceInput:
    final_slots = {s["key"]: s["value"] for s in data.get("final_slots", []) if s.get("value")}
    turns = _build_turns(data)
    retrieved_chunks = [
        RetrievedChunk(
            chunk_id=c["chunk_id"], source_type=c["source_type"], text=c["text"],
            score=c.get("score"),
        )
        for c in raw_chunks
    ]
    return DomainInferenceInput(
        session_id=session_id,
        final_slots=final_slots,
        session_ctrs=data.get("session_ctrs", 5),
        crisis_triggered=data.get("crisis_triggered", False),
        crisis_turn=data.get("crisis_turn"),
        is_first_visit=is_first_visit,
        turns=turns,
        # PLAN-2026-W28-Q W2: F1Result now persists the narrowed carry
        # content (`prior_handoff` = `_compose_carry_content` output,
        # final_slots+missing_slots only — AVC-02) — wired to the real
        # value; `None` for a first-visit session (never persisted).
        prior_handoff=data.get("prior_handoff"),
        probe_events=data.get("probe_events", []),
        scale_scores=scale_scores,
        retrieved_chunks=retrieved_chunks,
        retrieval_mode=mode,  # type: ignore[arg-type]
        queries=queries_used,
    )


# ── Stage 3: evidence whitelist + artifact ─────────────────────────────


def _repro_metadata(
    *,
    model_used: str,
    prompt_version: str,
    input_path: Path,
    mode: str,
    latency_ms: float,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
    raw_response: str | None = None,
    validation_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    git_head = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=5, check=True,
        )
        git_head = result.stdout.strip()
    except Exception as exc:  # noqa: BLE001 — repro metadata is best-effort
        logger.warning("f2.repro.git_head_failed — %s", exc)

    return {
        "git_head": git_head,
        "model_used": model_used,
        "prompt_version": prompt_version,
        "input_file": str(input_path),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "mode": mode,
        "latency_ms": round(latency_ms, 1),
        "generated_at": datetime.now().isoformat(),
        # BUG-017 phase A: the LLM call's finish_reason/usage, so a future
        # RAG-mode truncation hypothesis (finish_reason == "length") is
        # falsifiable directly from a saved artifact, not just from logs.
        "finish_reason": finish_reason,
        "usage": usage,
        # BUG-019: raw LLM response text (present only on a parse/schema
        # failure) + Pydantic ValidationError.errors() field-level detail
        # (schema-validation failures only), mirroring finish_reason/usage
        # above — closes the root-cause-undiagnosable gap BUG-019 found.
        "raw_response": raw_response,
        "validation_errors": validation_errors,
    }


def _build_filter_summary(
    *, candidates_before: list[DomainCandidate], candidates_after: list[DomainCandidate],
    counts: dict[str, int],
) -> dict[str, Any]:
    """Pre-to-post cascade deltas (ADR-014 wiring) — additive artifact field.

    Domain-keyed (mirrors ``find_orphan_departments``'s existing set-based
    domain matching in this module): if the LLM ever emits two candidates
    with the same domain, ``eliminated_domains`` may under-count — an
    accepted, out-of-scope edge case (schema does not forbid it, but the
    prompt/practice never produces duplicates).
    """
    after_domains = {c.domain for c in candidates_after}
    eliminated_domains = [c.domain for c in candidates_before if c.domain not in after_domains]
    n_evidence_stripped = sum(v for k, v in counts.items() if k != VERDICT_ACCEPTED)
    return {
        "candidates_before": len(candidates_before),
        "candidates_after": len(candidates_after),
        "candidates_eliminated": len(eliminated_domains),
        "eliminated_domains": eliminated_domains,
        "evidence_stripped": n_evidence_stripped,
        # Named out separately (not just inside whitelist_audit.counts) so
        # EXP-005 can read the ADR-014 risk-lexicon recurrence count directly
        # off filter_summary without re-deriving it from the verdict list.
        "evidence_stripped_risk_lexicon": counts.get(VERDICT_REJECTED_RISK_LEXICON, 0),
    }


# PLAN-2026-W28-H Track B (REV-013 §3/§4) — the "AI 예상질환" container.
# PLAN-2026-W28-K Task 3 (ADR-020/ADR-021) — live population, path1.
_AI_PREDICTED_DISEASE_REASON_UNPOPULATED = (
    "Stage 1 ran in llm_only mode (no RAG chunks retrieved this run) — the "
    "AI-disease container has no chunk-derived evidence to populate from"
)

# ADR-020 condition 3 (binding): the two-hop-proxy caveat must be disclosed
# on every POPULATED run, not merely understood internally.
_AI_PREDICTED_DISEASE_PROXY_CAVEAT = (
    "similarity_score is a RAG cosine-similarity signal between the "
    "retrieved chunk and the Stage-1 query — NOT a patient-to-disease "
    "similarity, and NOT a calibrated probability (two-hop proxy, "
    "RES-001 §2 step 9 / ADR-020 condition 3)."
)


def _build_ai_predicted_disease() -> AIPredictedDiseaseOutput:
    """Build the unpopulated "AI 예상질환" container.

    Used whenever Stage 1 ran in ``llm_only`` mode this run (no RAG chunks
    retrieved, per ``run_stage1``) — there is no chunk-derived evidence to
    populate from. A ``rag``-mode run instead calls
    :func:`_build_ai_predicted_disease_populated`. This function makes no DB
    call and always emits ``mode="experimental_unpopulated"`` with empty
    ``candidates`` and an honest ``reason_summary``. Standalone
    (`src.schemas.ai_predicted_disease`) — shares no type with
    `DomainInferenceOutput`/`DomainCandidate` above (REV-013 §3).
    """
    return AIPredictedDiseaseOutput(
        mode="experimental_unpopulated",
        candidates=[],
        reason_summary=_AI_PREDICTED_DISEASE_REASON_UNPOPULATED,
    )


def _extract_quote(text: str, term: str, *, window: int = 40) -> str:
    """Short verbatim excerpt of *text* centered on the first occurrence of
    *term* (RES-001 §2 step 8's provenance quote). Defensive fallback (a
    leading excerpt) if *term* is not actually found in *text* — should not
    happen on the live path (the term is only ever passed in because
    `retrieval.match_diseases_for_chunk_text` found it as a substring of
    this exact text), but keeps this pure function total for unit tests
    that construct synthetic (chunk, term) pairs directly.
    """
    idx = text.find(term)
    if idx == -1:
        excerpt = text[: window * 2].strip()
        return f"{excerpt}..." if len(text) > window * 2 else excerpt
    start = max(0, idx - window)
    end = min(len(text), idx + len(term) + window)
    excerpt = text[start:end].strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{excerpt}{suffix}"


def _clamp_similarity_score(score: float) -> float:
    """Clamp a chunk's raw cosine retrieval score to ``[0,1]`` (ADR-020
    condition 4 / REV-016 issue #4).

    pgvector cosine similarity (``1 - (embedding <=> vector)``) is
    theoretically bounded to ``[-1,1]``, and `retrieval.py`'s own SQL does
    not clamp it — `RetrievedChunk.score`/`DomainCandidate` evidence have
    never observed a negative value live, but
    ``AIPredictedDiseaseCandidate.similarity_score`` declares ``ge=0.0``, so
    an as-yet-unexercised negative-cosine chunk would otherwise raise an
    uncaught ``ValidationError`` mid-population and take down the whole
    step. Clamping (rather than excluding the candidate) is chosen because
    it is deterministic and keeps the candidate's disease/provenance
    auditable even in this edge case, at the cost of slightly overstating a
    near-zero-or-negative match as exactly 0.0 — an acceptable, disclosed
    trade-off for a value the two-hop-proxy caveat already flags as not a
    calibrated probability.
    """
    return max(0.0, min(1.0, score))


async def _collect_chunk_disease_votes(
    db: Any, raw_chunks: list[dict[str, Any]], *, limit_per_chunk: int = 2
) -> list[tuple[dict[str, Any], str, str]]:
    """For each Stage-1 chunk, up to ``limit_per_chunk`` (disease_name,
    matched_term) votes (RES-001 §2 steps 1-3) — reuses the SAME chunks
    DomainInferenceAgent already received, makes NO second vector query.

    Thin, DB-touching wrapper kept separate from the pure aggregation/
    filtering/scoring logic in :func:`_aggregate_disease_candidates` so the
    latter is unit-testable without a live DB or async mocking.
    """
    from src.rag.retrieval import match_diseases_for_chunk_text

    votes: list[tuple[dict[str, Any], str, str]] = []
    for chunk in raw_chunks:
        chunk_text = chunk.get("text") or ""
        if not chunk_text.strip():
            continue
        for disease_name, _overlap, term in await match_diseases_for_chunk_text(
            db, chunk_text, limit=limit_per_chunk
        ):
            votes.append((chunk, disease_name, term))
    return votes


def _aggregate_disease_candidates(
    votes: list[tuple[dict[str, Any], str, str]],
) -> tuple[list[AIPredictedDiseaseCandidate], int]:
    """RES-001 §2 steps 4-9 + ADR-020 conditions 1/2/4 — pure, DB-free,
    directly unit-testable.

    Args:
        votes: ``(chunk_dict, disease_name, matched_term)`` tuples, one per
            (chunk, disease) vote already collected by
            :func:`_collect_chunk_disease_votes` — each ``chunk_dict`` has
            at least ``chunk_id``/``text``/``score`` (the same shape
            ``retrieve_domain_chunks`` returns).

    Returns:
        ``(candidates, n_dropped_risk_lexicon)`` — candidates sorted by
        ``similarity_score`` descending, truncated to top-5, never padded;
        MAX-not-sum per disease name (RES-001 §2 step 5); every quote must
        clear the risk-lexicon filter (VAL-011/ADR-020 condition 1,
        blocking) — a vote whose quote is risk-flagged is DROPPED (never
        clipped/redacted), and ``n_dropped_risk_lexicon`` counts how many
        votes were dropped this way, so the caller can build an honest
        ``reason_summary``.
    """
    best: dict[str, AIPredictedDiseaseCandidate] = {}
    n_dropped = 0
    for chunk, disease_name, term in votes:
        chunk_text = chunk.get("text") or ""
        quote = _extract_quote(chunk_text, term)
        # VAL-011/ADR-020 condition 1 (blocking-scoped, REV-017 Finding 1
        # fix): the load-bearing check is against the FULL source chunk
        # text, not the ±40-char extracted quote window — ADR-020 condition
        # 1's own text is "any candidate whose sole matched chunk is
        # risk-lexicon-flagged is DROPPED", and a deterministic window
        # centered on the matched *symptom* term can sit far from where a
        # risk phrase actually appears in a longer chunk (case_card:664/563,
        # REV-017). The quote-only check is kept as defense-in-depth (also
        # drops if the risk phrase happens to fall inside the shipped
        # excerpt itself) but is no longer the sole gate. Mirrors
        # filter_domain_candidates' "no evidence, no candidate" discipline —
        # drop the vote outright, never clip/redact the quote/chunk.
        if _contains_any(chunk_text, _RISK_PHRASES) or _contains_any(quote, _RISK_PHRASES):
            n_dropped += 1
            continue

        raw_score = chunk.get("score")
        score = _clamp_similarity_score(float(raw_score) if raw_score is not None else 0.0)
        candidate = AIPredictedDiseaseCandidate(
            disease=disease_name,
            similarity_score=score,
            source_id=chunk.get("chunk_id"),
            quote=quote,
        )

        # MAX-not-sum aggregation across chunks (RES-001 §2 step 5) — a
        # disease mentioned in several chunks keeps only its single
        # highest-scoring vote, never a summed/averaged score.
        current = best.get(disease_name)
        if current is None or candidate.similarity_score > current.similarity_score:
            best[disease_name] = candidate

    ranked = sorted(best.values(), key=lambda c: c.similarity_score, reverse=True)
    return ranked[:5], n_dropped  # top-5, never padded (RES-001 §2 step 6)


async def _build_ai_predicted_disease_populated(
    db: Any, raw_chunks: list[dict[str, Any]], *, limit_per_chunk: int = 2
) -> AIPredictedDiseaseOutput:
    """Live top-5 disease population for a RAG-mode run — path1 (ADR-020),
    PLAN-2026-W28-K Task 3.

    A deterministic post-processing pass over the SAME Stage-1 ``raw_chunks``
    DomainInferenceAgent already used for ``domain_candidates`` — independent
    of, and not blocking on, the LLM call (REV-016(c); this function never
    touches the certified `domain_inference` prompt or ``DomainCandidate``
    output). A 0-candidate outcome (no chunk matched a canonical symptom
    keyword, or every match was risk-lexicon-dropped) is legitimate, not an
    error (RES-001 §2 step 7).
    """
    votes = await _collect_chunk_disease_votes(db, raw_chunks, limit_per_chunk=limit_per_chunk)
    candidates, n_dropped = _aggregate_disease_candidates(votes)
    n_chunks = len(raw_chunks)

    if candidates:
        reason = (
            f"{len(candidates)} disease candidate(s) derived from {n_chunks} "
            "retrieved chunk(s) via symptom-keyword match (path1, ADR-020). "
            f"{_AI_PREDICTED_DISEASE_PROXY_CAVEAT}"
        )
    else:
        reason = (
            f"0 of {n_chunks} retrieved chunk(s) yielded a disease candidate "
            "this run (no canonical symptom keyword matched, or every match "
            "was dropped by the risk-lexicon filter) — a legitimate "
            f"0-candidate outcome, not an error (RES-001 §2 step 7). "
            f"{_AI_PREDICTED_DISEASE_PROXY_CAVEAT}"
        )
    if n_dropped:
        reason += (
            f" {n_dropped} candidate vote(s) dropped by the risk-lexicon "
            "filter before ranking (VAL-011/ADR-020 condition 1)."
        )

    # PLAN-2026-W28-Q W5 (disease<->questionnaire linkage, answer #5a):
    # recommended_questionnaire is derived from the TOP-ranked candidate
    # only (candidates is already sorted descending by similarity_score by
    # _aggregate_disease_candidates) via the static classification->scale
    # mapping. None when there are no candidates this run, or when the top
    # candidate's disease name doesn't resolve to a construct-valid scale
    # (an explicit no-forced-mismatch result — src.rag.questionnaire_mapping).
    recommended_questionnaire = (
        resolve_questionnaire_for_disease_name_ko(candidates[0].disease) if candidates else None
    )

    return AIPredictedDiseaseOutput(
        mode="rag_live",
        candidates=candidates,
        reason_summary=reason,
        recommended_questionnaire=recommended_questionnaire,
    )


# Enhancement #4 code-side half (ADR-021, REV-016(a)) — evidence-provenance
# reporting. Computed entirely from data already schema-validated in the
# artifact (`DomainEvidence.source_type`/`source_id`) — zero LLM call, zero
# edit to the certified `domain_inference/v2.system.md` prompt.
def _build_evidence_provenance_summary(
    domain_candidates: list[DomainCandidate],
) -> dict[str, int]:
    """Provenance counts over POST-cascade (accepted-only) evidence.

    ``rag_chunk`` items are split on their ``source_id``'s DB-table-origin
    prefix (``case_card:<id>`` / ``qa:<id>``, confirmed BUG-016-clean as of
    EXP-008) into ``rag_chunk_case_card`` / ``rag_chunk_qa``; a malformed or
    unrecognized prefix (should not occur post-whitelist, but this function
    must not silently miscount if it does) falls into ``rag_chunk_other``
    rather than being dropped or merged into one of the two known buckets.

    ``ocr_document`` (PLAN-2026-W28-Q W1, `EvidenceSourceType` addition) gets
    its own counter — no OCR content is wired into F2's evidence-grounding
    input yet, so this bucket is 0 today by construction, but it must not
    silently vanish from the summary the moment a future run does cite one.
    """
    counts = {
        "rag_chunk_case_card": 0,
        "rag_chunk_qa": 0,
        "rag_chunk_other": 0,
        "utterance": 0,
        "ocr_document": 0,
    }
    for cand in domain_candidates:
        for ev in cand.evidence:
            if ev.source_type == "rag_chunk":
                prefix = ev.source_id.split(":", 1)[0]
                if prefix == "case_card":
                    counts["rag_chunk_case_card"] += 1
                elif prefix == "qa":
                    counts["rag_chunk_qa"] += 1
                else:
                    counts["rag_chunk_other"] += 1
            elif ev.source_type == "utterance":
                counts["utterance"] += 1
            elif ev.source_type == "ocr_document":
                counts["ocr_document"] += 1
    return counts


def _build_artifact(
    *,
    output: DomainInferenceOutput,
    domain_candidates: list[DomainCandidate],
    repro: dict[str, Any],
    chunk_texts: dict[str, str],
    utterances: dict[str, str],
    verdicts: list[Any],
    counts: dict[str, int],
    filter_summary: dict[str, Any],
    orphans: list[Any],
    session_id: str,
    persona_id: str | None,
    ai_predicted_disease: dict[str, Any] | None = None,
    evidence_provenance_summary: dict[str, int] | None = None,
    rag_trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the F2 artifact dict.

    ``domain_candidates`` must already be POST-cascade (the output of
    ``filter_domain_candidates``, ADR-014) — this is what ships in the JSON,
    not the raw LLM output. ``filter_summary`` records the pre->post delta
    for transparency; ``verdicts``/``counts`` under ``whitelist_audit`` still
    cover every evidence item submitted (accepted + all rejection reasons),
    so the full audit trail is preserved even though rejected evidence never
    reaches ``domain_candidates``.

    ``ai_predicted_disease`` (PLAN-2026-W28-H Track B, REV-013 §3): the
    ``AIPredictedDiseaseOutput.model_dump()`` dict, attached as a SIBLING
    top-level key — never nested inside ``domain_candidates`` or any other
    key above. Defaults to ``None`` only for backward-compat with call
    sites/tests that predate this field; ``_run()`` always passes a real
    value.

    ``evidence_provenance_summary`` (enhancement #4 code-side half, ADR-021):
    :func:`_build_evidence_provenance_summary`'s output dict. Defaults to
    ``None`` for the same backward-compat reason; ``_run()`` always supplies
    a real value.

    ``rag_trigger`` (PLAN-2026-W28-Q W4): ``TriggerDecision.as_dict()``
    (`src.rag_trigger`) — the active policy (A/B), the effective retrieve
    decision, the post-filter query list, dropped (risk-lexicon-flagged)
    queries, and (Policy B only) the judge's own I/O, persisted as an audit
    surface (this wave's binding requirement). SIBLING top-level key, same
    convention as ``ai_predicted_disease``/``evidence_provenance_summary``
    above. ``None`` only for pre-W4 artifacts/tests; ``_run()`` always
    supplies a real value.
    """
    return {
        "session_id": session_id,
        "persona_id": persona_id,
        "repro": repro,
        "domain_candidates": [c.model_dump() for c in domain_candidates],
        "department_candidates": [c.model_dump() for c in output.department_candidates],
        "summary": output.summary,
        "retrieval_meta": output.retrieval_meta.model_dump(),
        # Stored for audit replay (REV-006 #1) — the actual text every rag_chunk
        # evidence quote was checked against, not just the chunk_id.
        "chunk_texts": chunk_texts,
        "utterances": utterances,
        "whitelist_audit": {
            "counts": counts,
            "verdicts": [
                {
                    "domain": v.domain, "source_type": v.source_type, "source_id": v.source_id,
                    "quote": v.quote, "verdict": v.verdict, "reason": v.reason,
                }
                for v in verdicts
            ],
        },
        # ADR-014 cascade summary — pre/post candidate + evidence deltas
        # (additive field; does not replace whitelist_audit).
        "filter_summary": filter_summary,
        "orphan_departments": [d.model_dump() for d in orphans],
        "additional_questions": output.additional_questions,
        "model_used": output.model_used,
        "prompt_version": output.prompt_version,
        "latency_ms": output.latency_ms,
        # BUG-017 phase A: mirrors repro["finish_reason"/"usage"] at the
        # top level too, alongside model_used/prompt_version/latency_ms.
        "finish_reason": output.finish_reason,
        "usage": output.usage,
        # BUG-019: mirrors repro["raw_response"/"validation_errors"] at the
        # top level too.
        "raw_response": output.raw_response,
        "validation_errors": output.validation_errors,
        # PLAN-2026-W28-H Track B (REV-013 §3) — SIBLING top-level key, not
        # nested inside domain_candidates/summary/any handoff-shaped object.
        # `None` only for pre-Track-B artifacts/tests; `_run()` always
        # supplies a real (possibly experimental_unpopulated) value.
        "ai_predicted_disease": ai_predicted_disease,
        # Enhancement #4 code-side half (ADR-021) — additive, read-only over
        # data already validated above; `None` only for pre-#4 artifacts/tests.
        "evidence_provenance_summary": evidence_provenance_summary,
        # PLAN-2026-W28-Q W4 — SIBLING top-level key, additive; `None` only
        # for pre-W4 artifacts/tests. `rag_trigger.retrieve` vs `repro.mode`
        # vs `ai_predicted_disease.mode` is the MET-6 mode-consistency triple.
        "rag_trigger": rag_trigger,
    }


def _build_report(artifact: dict[str, Any]) -> str:
    repro = artifact["repro"]
    filter_summary = artifact.get("filter_summary", {})
    # ADR-014: all evidence submitted this run, grouped by domain — used below
    # to surface stripped/eliminated items. `artifact["domain_candidates"]`
    # is POST-cascade (survivors only, accepted evidence only), so this is
    # the only place the report can still see what got removed.
    verdicts_by_domain: dict[str, list[dict[str, Any]]] = {}
    for v in artifact["whitelist_audit"]["verdicts"]:
        verdicts_by_domain.setdefault(v["domain"], []).append(v)

    lines = [
        f"# F2 Domain Inference Report — {artifact.get('persona_id') or artifact['session_id']}",
        "",
        "## Repro metadata",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| git HEAD | `{repro['git_head']}` |",
        f"| model_used | {repro['model_used']} |",
        f"| prompt_version | {repro['prompt_version']} |",
        f"| input_file | `{repro['input_file']}` |",
        f"| input_sha256 | `{repro['input_sha256']}` |",
        f"| mode | **{repro['mode']}** |",
        f"| latency_ms | {repro['latency_ms']} |",
        f"| generated_at | {repro['generated_at']} |",
        # BUG-017 phase A diagnostic instrumentation — repro.get(...) (not
        # repro[...]) so artifacts/tests built from a pre-BUG-017 repro dict
        # (missing these keys) don't KeyError.
        f"| finish_reason | {repro.get('finish_reason')} |",
        f"| usage | {repro.get('usage')} |",
        "",
        "## Retrieval",
        "",
        f"- mode: {artifact['retrieval_meta']['mode']}",
        f"- chunks_returned: {artifact['retrieval_meta']['chunks_returned']}",
        f"- chunk_ids: {artifact['retrieval_meta']['chunk_ids']}",
        f"- queries: {artifact['retrieval_meta'].get('queries')}",
        "",
        "## Domain candidates",
        "",
    ]
    if artifact["domain_candidates"]:
        for c in artifact["domain_candidates"]:
            lines.append(f"### {c['domain']} (confidence={c['confidence']})")
            # Every evidence item still on a surviving candidate has already
            # passed the whitelist + risk-lexicon cascade (ADR-014) — nothing
            # rejected reaches here, so every line below is, by construction, OK.
            for ev in c["evidence"]:
                lines.append(
                    f"- [OK] {ev['source_type']}:{ev['source_id']} — \"{ev['quote']}\""
                )
            stripped = [
                v for v in verdicts_by_domain.get(c["domain"], []) if v["verdict"] != "accepted"
            ]
            if stripped:
                lines.append(
                    f"- **{len(stripped)} evidence item(s) STRIPPED by grounding cascade "
                    "(ADR-014):**"
                )
                for v in stripped:
                    lines.append(
                        f"  - [STRIPPED:{v['verdict']}] {v['source_type']}:{v['source_id']} "
                        f"— \"{v['quote']}\" ({v['reason']})"
                    )
            if c.get("recommended_surveys"):
                lines.append(f"- recommended_surveys: {c['recommended_surveys']}")
            lines.append("")
    else:
        lines.append("(no candidates)")
        lines.append("")

    eliminated_domains = filter_summary.get("eliminated_domains", [])
    if eliminated_domains:
        lines.extend(["### Eliminated candidates (all evidence rejected by cascade)", ""])
        for domain in eliminated_domains:
            lines.append(f"#### {domain} — ELIMINATED")
            for v in verdicts_by_domain.get(domain, []):
                lines.append(
                    f"- [{v['verdict']}] {v['source_type']}:{v['source_id']} "
                    f"— \"{v['quote']}\" ({v['reason']})"
                )
            lines.append("")

    lines.extend(["## Department candidates", ""])
    if artifact["department_candidates"]:
        for d in artifact["department_candidates"]:
            orphan = d in artifact["orphan_departments"]
            tag = " **[ORPHAN domain_ref]**" if orphan else ""
            lines.append(
                f"- {d['department']} (domain_ref={d.get('domain_ref')}){tag} — {d['reason']}"
            )
    else:
        lines.append("(no candidates)")
    lines.append("")

    lines.extend([
        "## Summary",
        "",
        artifact["summary"] or "(empty)",
        "",
        "## Whitelist audit",
        "",
        f"- counts: {artifact['whitelist_audit']['counts']}",
        f"- orphan departments: {len(artifact['orphan_departments'])}",
        "",
    ])

    # Enhancement #4 code-side half (ADR-021, REV-016(a)) — additive,
    # computed from data already validated above; `None` only for pre-#4
    # artifacts/tests.
    eps = artifact.get("evidence_provenance_summary")
    if eps is not None:
        lines.extend([
            "## Evidence provenance (enhancement #4)",
            "",
            f"- rag_chunk(case_card): {eps.get('rag_chunk_case_card', 0)}",
            f"- rag_chunk(qa): {eps.get('rag_chunk_qa', 0)}",
            f"- rag_chunk(other/unrecognized prefix): {eps.get('rag_chunk_other', 0)}",
            f"- utterance: {eps.get('utterance', 0)}",
            f"- ocr_document: {eps.get('ocr_document', 0)}",
            "",
        ])

    lines.extend([
        "## Grounding cascade (ADR-014)",
        "",
        f"- candidates before -> after: {filter_summary.get('candidates_before', '?')} -> "
        f"{filter_summary.get('candidates_after', '?')} "
        f"({filter_summary.get('candidates_eliminated', 0)} eliminated)",
        f"- eliminated domains: {eliminated_domains or '(none)'}",
        f"- evidence stripped (all reasons): {filter_summary.get('evidence_stripped', 0)}",
        "- evidence stripped (risk-lexicon, ADR-014 recurrence count): "
        f"{filter_summary.get('evidence_stripped_risk_lexicon', 0)}",
        "",
    ])

    # BUG-019: only rendered when a parse/schema failure actually occurred
    # this run — keeps the report unchanged for the (common) clean-success
    # case, matching this module's own "additive, honest-on-failure-only"
    # convention already used elsewhere (e.g. filter_summary's eliminated-
    # domains section above).
    if artifact.get("raw_response") is not None:
        lines.extend([
            "## LLM failure diagnostics (BUG-019)",
            "",
            f"- validation_errors: {artifact.get('validation_errors')}",
            "- raw_response:",
            "",
            "```",
            str(artifact["raw_response"]),
            "```",
            "",
        ])

    # PLAN-2026-W28-H Track B (REV-013 §3) — SIBLING section, kept visually
    # and structurally separate from the domain/department candidates above
    # (not merged into "## Domain candidates").
    ai_disease = artifact.get("ai_predicted_disease")
    if ai_disease is not None:
        lines.extend([
            "## AI 예상질환 (experimental, non-diagnostic)",
            "",
            f"- mode: **{ai_disease.get('mode')}**",
            f"- is_diagnostic: {ai_disease.get('is_diagnostic')}",
            f"- disclaimer: {ai_disease.get('disclaimer')}",
            f"- reason_summary: {ai_disease.get('reason_summary')}",
        ])
        candidates = ai_disease.get("candidates") or []
        if candidates:
            for c in candidates:
                line = f"- {c['disease']} (similarity_score={c['similarity_score']})"
                if c.get("source_id") or c.get("quote"):
                    line += f" — {c.get('source_id')} — \"{c.get('quote')}\""
                lines.append(line)
        else:
            lines.append("- (no candidates)")
        lines.append("")

    # PLAN-2026-W28-Q W4 — SIBLING section, additive; `None` only for
    # pre-W4 artifacts/tests.
    rag_trigger = artifact.get("rag_trigger")
    if rag_trigger is not None:
        lines.extend([
            "## RAG trigger (PLAN-2026-W28-Q W4)",
            "",
            f"- policy: **{rag_trigger.get('policy')}**",
            f"- retrieve: {rag_trigger.get('retrieve')}",
            f"- trigger_reason: {rag_trigger.get('trigger_reason')}",
            f"- fallback_used: {rag_trigger.get('fallback_used')}",
            f"- queries: {rag_trigger.get('queries')}",
        ])
        dropped = rag_trigger.get("dropped_queries") or []
        if dropped:
            lines.append(
                f"- **{len(dropped)} query(ies) DROPPED by the single-choke-point "
                f"risk-lexicon filter (REV-022 Issues 9/10):** {dropped}"
            )
        judge_output = rag_trigger.get("judge_output")
        if judge_output is not None:
            lines.append(f"- judge_output: {judge_output}")
        lines.append("")

    return "\n".join(lines)


def save_f2_result(artifact: dict[str, Any], output_dir: Path | None = None) -> dict[str, Path]:
    base = output_dir or OUTPUT_DIR
    vp_id = artifact.get("persona_id") or artifact["session_id"]
    out = base / vp_id
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{vp_id}_{ts}"

    json_path = out / f"{prefix}_domain_inference.json"
    json_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    report_path = out / f"{prefix}_report.md"
    report_path.write_text(_build_report(artifact), encoding="utf-8")

    return {"json": json_path, "report": report_path}


# ── CLI entry point ──────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> None:
    data, input_path = _load_input(args)

    persona_id = data.get("persona_id")
    session_id = data.get("session_id") or persona_id or "f2_session"
    is_first_visit = (
        True if args.first_visit else False if args.revisit else _infer_is_first_visit(data)
    )
    scale_scores = _load_scale_scores(args.scale_scores)

    final_slots = {s["key"]: s["value"] for s in data.get("final_slots", []) if s.get("value")}
    turns_for_trigger = _build_turns(data)
    probe_events = data.get("probe_events", [])

    # PLAN-2026-W28-Q W4 — config-driven RAG trigger arm (default A). Both
    # arms funnel through the SAME single-choke-point risk-lexicon filter
    # (`src.rag_trigger.apply_risk_lexicon_filter`, REV-022 Issues 9/10)
    # regardless of policy — this is what makes cc/HPI-content exposure
    # mitigated identically for both arms, not scattered per-source.
    # `--no-rag` is checked FIRST so Policy B never spends an LLM call when
    # retrieval is disabled outright.
    rag_trigger_policy = getattr(args, "rag_trigger_policy", "A") or "A"
    if args.no_rag:
        trigger = no_rag_decision(rag_trigger_policy)
    elif rag_trigger_policy == "B":
        judge_agent = RagTriggerJudgeAgent(
            model_router=get_model_router(), prompt_loader=get_prompt_loader()
        )
        trigger = await decide_policy_b(
            judge_agent, session_id=session_id, final_slots=final_slots,
            turns=turns_for_trigger,
        )
    else:
        trigger = decide_policy_a(final_slots, turns_for_trigger, probe_events)

    if trigger.retrieve:
        mode, raw_chunks = await run_stage1(
            final_slots, no_rag=False, k=args.k, queries_override=trigger.queries
        )
    else:
        mode, raw_chunks = "llm_only", []
    queries_used = trigger.queries if mode == "rag" else []

    inp = _build_input(
        data, session_id=session_id, is_first_visit=is_first_visit,
        scale_scores=scale_scores, mode=mode, raw_chunks=raw_chunks,
        queries_used=queries_used,
    )

    agent = DomainInferenceAgent(model_router=get_model_router(), prompt_loader=get_prompt_loader())
    output = await agent.run(inp)

    chunk_texts = {c["chunk_id"]: c["text"] for c in raw_chunks}
    utterances = {f"turn_{t.turn}": t.patient_message for t in inp.turns}
    # ADR-014 wiring: apply the rejection cascade (incl. the risk-lexicon
    # filter) HERE, before the artifact is built — `filtered_candidates` is
    # what ships in domain_candidates, not the raw LLM output. `verdicts`/
    # `counts` still cover every evidence item submitted (accepted + all
    # rejection reasons), so whitelist_audit keeps the full trail.
    filtered_candidates, verdicts, counts = filter_domain_candidates(
        output.domain_candidates, chunk_texts=chunk_texts, utterances=utterances
    )
    # Orphan check runs against the POST-cascade domain list: a department
    # candidate referencing a domain that the cascade eliminated is an
    # orphan in the live output, even if it wasn't pre-cascade.
    orphans = find_orphan_departments(filtered_candidates, output.department_candidates)
    filter_summary = _build_filter_summary(
        candidates_before=output.domain_candidates, candidates_after=filtered_candidates,
        counts=counts,
    )

    repro = _repro_metadata(
        model_used=output.model_used, prompt_version=output.prompt_version,
        input_path=input_path, mode=mode, latency_ms=output.latency_ms,
        finish_reason=output.finish_reason, usage=output.usage,
        raw_response=output.raw_response, validation_errors=output.validation_errors,
    )
    # PLAN-2026-W28-K Task 3 (ADR-020) — live population for a RAG-mode run;
    # llm_only stays experimental_unpopulated (no chunks to derive from).
    # This is a SEPARATE DB session from Stage 1's (already closed by
    # run_stage1's own `async with`) and runs entirely independent of the
    # certified DomainInferenceAgent call above (REV-016(c)).
    if mode == "rag" and raw_chunks:
        try:
            sessionmaker = get_sessionmaker()
            async with sessionmaker() as db:
                ai_predicted_disease = await _build_ai_predicted_disease_populated(
                    db, raw_chunks
                )
        except Exception as exc:  # noqa: BLE001 — population failure must not crash F2
            logger.warning(
                "f2.ai_predicted_disease.population_failed — falling back to "
                "experimental_unpopulated (RAG domain_candidates unaffected): %s", exc,
            )
            ai_predicted_disease = _build_ai_predicted_disease()
    else:
        ai_predicted_disease = _build_ai_predicted_disease()

    evidence_provenance_summary = _build_evidence_provenance_summary(filtered_candidates)

    artifact = _build_artifact(
        output=output, domain_candidates=filtered_candidates, repro=repro,
        chunk_texts=chunk_texts, utterances=utterances,
        verdicts=verdicts, counts=counts, filter_summary=filter_summary, orphans=orphans,
        session_id=session_id, persona_id=persona_id,
        ai_predicted_disease=ai_predicted_disease.model_dump(),
        evidence_provenance_summary=evidence_provenance_summary,
        rag_trigger=trigger.as_dict(),
    )

    out_dir = Path(args.out) if args.out else None
    paths = save_f2_result(artifact, out_dir)

    n_rejected = sum(v for k, v in counts.items() if k != "accepted")
    print(f"\n{'=' * 60}")
    print(f"  F2 Domain Inference: {persona_id or session_id}")
    print(f"{'=' * 60}")
    print(f"  Mode: {mode}")
    print(
        f"  Domain candidates: {len(filtered_candidates)} "
        f"(pre-cascade: {filter_summary['candidates_before']}, "
        f"eliminated: {filter_summary['candidates_eliminated']})"
    )
    print(f"  Department candidates: {len(output.department_candidates)} "
          f"(orphan: {len(orphans)})")
    print(f"  Whitelist: {counts.get('accepted', 0)} accepted / {n_rejected} rejected")
    print(f"  Model: {output.model_used} | prompt_version: {output.prompt_version}")
    print(f"  Latency: {output.latency_ms:.0f}ms")
    print(f"  Files: {paths['json'].name}, {paths['report'].name}")
    print(f"{'=' * 60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="F2 pipeline — RAG 기반 정신건강 영역/진료과 후보 추론"
    )
    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--conversation", help="F1 conversation.json 경로")
    src_group.add_argument("--persona", help="VP-001 등 — 최신 F1 결과를 체이닝")
    parser.add_argument(
        "--no-rag", action="store_true", help="Stage 1 검색 건너뛰기(mode=llm_only)"
    )
    parser.add_argument("--k", type=int, default=3, help="Stage 1 테이블별 top-k (기본 3)")
    parser.add_argument(
        "--rag-trigger-policy",
        choices=["A", "B"],
        default="A",
        dest="rag_trigger_policy",
        help=(
            "RAG 트리거 arm (PLAN-2026-W28-Q W4) — A: 슬롯 기반 + 전체 대화 fallback "
            "(기본값, 코드 레벨). B: LLM 판정(rag_trigger_judge)."
        ),
    )
    parser.add_argument("--out", default=None, help="출력 디렉터리 override")
    parser.add_argument("--scale-scores", default=None, help="F3 척도 점수 JSON 경로(선택)")
    visit_group = parser.add_mutually_exclusive_group()
    visit_group.add_argument(
        "--first-visit", action="store_true", help="is_first_visit=True로 강제"
    )
    visit_group.add_argument(
        "--revisit", action="store_true", help="is_first_visit=False로 강제"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # BUG-021: fail-fast path-existence validation, not the old unset-only
    # guard (which silently let an explicit-but-wrong PROMPTS_BASE_DIR
    # through and degraded every prompt-driven agent to a generic fallback).
    resolve_prompts_base_dir(PROJECT_ROOT)

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
