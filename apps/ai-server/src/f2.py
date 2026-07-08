"""F2 pipeline — RAG 기반 정신건강 영역(domain)/진료과(department) 후보 추론.

PLAN-2026-W28-C (discussion.md) 검증 파이프라인, `f1.py` 패턴을 따른다:

    입력 로드 → Stage 1 검색(rag/retrieval.py 재사용, 실패 시 mode=llm_only 강등,
    ANY failure never crashes) → Stage 2 LLM(DomainInferenceAgent) →
    근거-화이트리스트 검사(src.eval.f2_grounding, 코드 레벨, REV-006 #1) →
    산출물(JSON + report.md, 재현 메타 포함) → 콘솔 요약.

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
from src.dependencies import get_model_router, get_prompt_loader, get_sessionmaker
from src.eval.f2_grounding import audit_domain_candidates, find_orphan_departments
from src.f1 import OUTPUT_DIR
from src.schemas.domain_inference import (
    DomainInferenceInput,
    DomainInferenceOutput,
    RetrievedChunk,
    UtteranceTurn,
)
from src.schemas.handoff import ScaleScore

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # apps/ai-server/src/f2.py → neurosync/

# C-2: Stage 1 queries are drawn from these three F1 slots only.
_STAGE1_QUERY_SLOTS = ("chief_complaint", "history_of_present_illness", "risk_assessment")

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
    """F1Result doesn't persist is_revisit directly — infer from the turn-0
    greeting branch (f1.py `run_session`: the revisit branch's opening message
    quotes the prior handoff summary). Overridable via --first-visit/--revisit.
    """
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
    final_slots: dict[str, str], *, no_rag: bool, k: int
) -> tuple[str, list[dict[str, Any]]]:
    """Returns (mode, chunks). mode is 'llm_only' on --no-rag, empty queries, or
    ANY Stage-1 failure (DB/embedding) — never raises, never crashes the run
    (REV-006 condition 6: the fallback is explicit and reported, not silent).
    """
    if no_rag:
        logger.info("f2.stage1.skipped — --no-rag flag set, mode=llm_only")
        return "llm_only", []

    queries = [final_slots[k2] for k2 in _STAGE1_QUERY_SLOTS if final_slots.get(k2)]
    if not queries:
        logger.warning(
            "f2.stage1.no_queries — chief_complaint/HPI/risk_assessment all empty, "
            "mode=llm_only"
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
        prior_handoff=None,  # not persisted in F1 conversation.json — G-D scope
        probe_events=data.get("probe_events", []),
        scale_scores=scale_scores,
        retrieved_chunks=retrieved_chunks,
        retrieval_mode=mode,  # type: ignore[arg-type]
        queries=queries_used,
    )


# ── Stage 3: evidence whitelist + artifact ─────────────────────────────


def _repro_metadata(
    *, model_used: str, prompt_version: str, input_path: Path, mode: str, latency_ms: float
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
    }


def _build_artifact(
    *,
    output: DomainInferenceOutput,
    repro: dict[str, Any],
    chunk_texts: dict[str, str],
    utterances: dict[str, str],
    verdicts: list[Any],
    counts: dict[str, int],
    orphans: list[Any],
    session_id: str,
    persona_id: str | None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "persona_id": persona_id,
        "repro": repro,
        "domain_candidates": [c.model_dump() for c in output.domain_candidates],
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
        "orphan_departments": [d.model_dump() for d in orphans],
        "additional_questions": output.additional_questions,
        "model_used": output.model_used,
        "prompt_version": output.prompt_version,
        "latency_ms": output.latency_ms,
    }


def _build_report(artifact: dict[str, Any]) -> str:
    repro = artifact["repro"]
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
            for ev in c["evidence"]:
                verdict = next(
                    (
                        v for v in artifact["whitelist_audit"]["verdicts"]
                        if v["domain"] == c["domain"] and v["source_id"] == ev["source_id"]
                        and v["quote"] == ev["quote"]
                    ),
                    None,
                )
                mark = "OK" if verdict and verdict["verdict"] == "accepted" else "REJECTED"
                lines.append(
                    f"- [{mark}] {ev['source_type']}:{ev['source_id']} — \"{ev['quote']}\""
                )
            if c.get("recommended_surveys"):
                lines.append(f"- recommended_surveys: {c['recommended_surveys']}")
            lines.append("")
    else:
        lines.append("(no candidates)")
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
    mode, raw_chunks = await run_stage1(final_slots, no_rag=args.no_rag, k=args.k)
    queries_used = [final_slots[k] for k in _STAGE1_QUERY_SLOTS if final_slots.get(k)]

    inp = _build_input(
        data, session_id=session_id, is_first_visit=is_first_visit,
        scale_scores=scale_scores, mode=mode, raw_chunks=raw_chunks,
        queries_used=queries_used if mode == "rag" else [],
    )

    agent = DomainInferenceAgent(model_router=get_model_router(), prompt_loader=get_prompt_loader())
    output = await agent.run(inp)

    chunk_texts = {c["chunk_id"]: c["text"] for c in raw_chunks}
    utterances = {f"turn_{t.turn}": t.patient_message for t in inp.turns}
    verdicts, counts = audit_domain_candidates(
        output.domain_candidates, chunk_texts=chunk_texts, utterances=utterances
    )
    orphans = find_orphan_departments(output.domain_candidates, output.department_candidates)

    repro = _repro_metadata(
        model_used=output.model_used, prompt_version=output.prompt_version,
        input_path=input_path, mode=mode, latency_ms=output.latency_ms,
    )
    artifact = _build_artifact(
        output=output, repro=repro, chunk_texts=chunk_texts, utterances=utterances,
        verdicts=verdicts, counts=counts, orphans=orphans,
        session_id=session_id, persona_id=persona_id,
    )

    out_dir = Path(args.out) if args.out else None
    paths = save_f2_result(artifact, out_dir)

    n_rejected = sum(v for k, v in counts.items() if k != "accepted")
    print(f"\n{'=' * 60}")
    print(f"  F2 Domain Inference: {persona_id or session_id}")
    print(f"{'=' * 60}")
    print(f"  Mode: {mode}")
    print(f"  Domain candidates: {len(output.domain_candidates)}")
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

    import os
    if not os.environ.get("PROMPTS_BASE_DIR"):
        os.environ["PROMPTS_BASE_DIR"] = str(PROJECT_ROOT / "docs" / "ai" / "prompts")

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
