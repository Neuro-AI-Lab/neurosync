"""continuous_test.py — F1 -> F2 -> ... -> F6 end-to-end validation harness.

PLAN-2026-W28-H Track C. Chains the pipeline stages that exist today: runs an
F1 session for a persona (`f1.py`, `F1Pipeline`) and feeds the resulting F1
`conversation.json` into F2 (`f2.py`). F3-F6 do not exist yet in this repo —
they are explicit, LOGGED skip stubs in `STAGE_REGISTRY` (never silently
omitted): add a `Stage(...)` entry with `implemented=True` and a `run`
coroutine the moment `fN.py` ships, and the chain picks it up automatically.

This is a VALIDATION HARNESS, like `f1.py`'s simulation CLI and `f2.py` —
it is NOT wired into `orchestrator.py` or the 11-state machine.

Runs entirely IN-PROCESS against the live local Postgres DB, `.env`-driven
(`DATABASE_URL` via `src.dependencies.get_sessionmaker()`/`get_settings()`,
ADR-017: RAG is in-process only). The DB password is never printed, logged,
or committed by this file — see `_mask_dsn()`. This also requires the same
live LLM credentials `f1.py`/`f2.py` need (UPSTAGE_API_KEY for embeddings/
PatientLLM, an LLM adapter key for the pipeline agents) — it is a live
integration harness, not a DB/API mock; do not run it without those
configured.

F2's Stage-1 RAG retrieval silently downgrades to `mode=llm_only` on ANY
DB/embedding failure (`f2.py:183-188`, by design — never crashes the run).
That is correct for F2 in isolation, but in a harness meant to catch DB
outages it would make a dead DB look like a normal completion. This harness
runs its own DB preflight (`_db_preflight`) before the F2 stage and cross-
checks it against the artifact's actual `mode`, so a DB outage is reported
as an explicit WARN, not folded into a silent PASS.

Safe to re-run: F1/F2 both save timestamped output files (never overwrite),
so re-running this harness never clobbers a prior run's artifacts.

Multi-session chaining (PLAN-2026-W28-Q W2, `--sessions N`): chains N F1
sessions via the existing PUBLIC `followup_from` seam (session N+1 follows
up from session N's own saved `conversation.json`), running F2 after each
and appending one entry to a per-VP session ledger
(`<OUTPUT_DIR>/<persona>/<persona>_session_ledger.json`) — session ordinal,
simulated date, final/missing slots, repro metadata. The ledger is a
HARNESS ARTIFACT ONLY (`run_multi_session_chain`'s own docstring, REV-022
standing rule) — production code (`f1.py`/`f2.py`) never reads it.

Usage:
    cd apps/ai-server
    .venv/bin/python -m src.continuous_test --persona VP-001
    .venv/bin/python -m src.continuous_test --persona VP-001 --max-turns 6 --k 5
    # Re-run F2 only against an existing F1 artifact (repeated bug/DB-setup
    # iteration, PLAN-2026-W28-H Track C intent) — skips F1 entirely:
    .venv/bin/python -m src.continuous_test --persona VP-001 \\
        --start-from-conversation docs/ai/simulation_results/VP-001/VP-001_..._conversation.json
    # Chain 3 sessions (multi-session continuity + question induction),
    # 14 simulated days apart by default:
    .venv/bin/python -m src.continuous_test --persona VP-001 --sessions 3
"""

from __future__ import annotations

import argparse
import asyncio
import glob as _glob
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

# Multi-session chaining default (PLAN-2026-W28-Q W2, plan §3 "Multi-session
# + question induction") — 2 simulated weeks between chained sessions.
DEFAULT_SESSION_INTERVAL_DAYS = 14

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/continuous_test.py -> neurosync/


# ── DSN masking — DB password NEVER printed/logged/committed ──────────


def _mask_dsn(dsn: str) -> str:
    """Return `dsn` with any password component replaced by '***' — safe to log."""
    try:
        parts = urlsplit(dsn)
        if parts.password:
            netloc = parts.netloc.replace(f":{parts.password}@", ":***@")
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        return dsn
    except Exception:  # noqa: BLE001 — logging helper must never itself crash the run
        return "***unparseable-dsn***"


async def _db_preflight() -> tuple[bool, str]:
    """Trivial DB round-trip via the SAME sessionmaker F1/F2 use (`.env`
    DATABASE_URL, `src.dependencies.get_sessionmaker()`). Never logs the
    password — only a masked DSN and pass/fail go into the returned detail.
    """
    from sqlalchemy import text

    from src.dependencies import get_sessionmaker, get_settings

    masked = _mask_dsn(get_settings().database_url)
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            await db.execute(text("SELECT 1"))
        return True, f"reachable ({masked})"
    except Exception as exc:  # noqa: BLE001 — preflight result, not a crash
        return False, f"UNREACHABLE ({masked}): {exc}"


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


# ── Per-VP session ledger — HARNESS ARTIFACT ONLY ──────────────────────
#
# PLAN-2026-W28-Q W2 (plan §3 "Multi-session + question induction" row,
# `docs/ai/validation_plan_f1f2_continuous.md`): an append-only per-VP
# record of session ordinal, simulated date, final/missing slots, and repro
# metadata, for this harness's OWN multi-session bookkeeping.
#
# REV-022 standing rule (plan §5 "Other battery-level gates" /
# invariant 1): production code (f1.py, f2.py, orchestrator.py) MUST NEVER
# READ this file — it is not a product session store. Only this module
# (continuous_test.py) writes/reads it.


def _ledger_path(persona_id: str, out_dir: Path | None) -> Path:
    """`<OUTPUT_DIR>/<persona_id>/<persona_id>_session_ledger.json`."""
    from src.f1 import OUTPUT_DIR

    base = out_dir or OUTPUT_DIR
    return base / persona_id / f"{persona_id}_session_ledger.json"


def _load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — a corrupt ledger must not crash the harness
        logger.warning("continuous_test.ledger.unreadable — %s (starting fresh)", path)
        return []


def _append_ledger_entry(path: Path, entry: dict[str, Any]) -> None:
    """Append-only (read-modify-write the whole list — ledgers are small,
    bounded by the number of chained sessions per VP, never a live DB)."""
    entries = _load_ledger(path)
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


# ── Stage result / chain context ───────────────────────────────────────


@dataclass
class StageResult:
    """Outcome of one chain stage — surfaced verbatim in the console report."""

    name: str
    status: str  # "pass" | "warn" | "fail" | "skip"
    detail: str
    artifacts: dict[str, Path] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class ChainContext:
    """Carries state between stages (e.g. F1's conversation.json path -> F2).

    Trivially extensible: a future F3 stage reads/writes new fields here
    (e.g. `scale_scores_path` is already wired for F2's optional F3 input).
    """

    persona_id: str
    max_turns: int
    k: int
    out_dir: Path | None
    scale_scores_path: str | None
    # set by F1 (or --start-from-conversation), consumed by F2
    conversation_path: Path | None = None
    domain_inference_path: Path | None = None  # set by F2


StageFn = Callable[[ChainContext], Awaitable[StageResult]]


@dataclass
class Stage:
    """One entry in the chain registry.

    Trivially extensible: append a `Stage("F3", True, run_f3_stage)` to
    `STAGE_REGISTRY` the moment `f3.py` ships. Until then, unimplemented
    stages carry `run=None` and are LOGGED skip stubs — `run_chain` always
    emits one `StageResult` per registry entry, so an unimplemented stage
    never silently disappears from the report.
    """

    name: str
    implemented: bool
    run: StageFn | None
    note: str = ""


# ── F1 stage ────────────────────────────────────────────────────────────


def _find_latest_f1_conversation(persona_id: str) -> Path | None:
    """Same glob convention `f1.py`/`f2.py` already use (VP subdir + legacy flat)."""
    from src.f1 import OUTPUT_DIR

    pattern_sub = str(OUTPUT_DIR / persona_id / f"{persona_id}_*_conversation.json")
    pattern_flat = str(OUTPUT_DIR / f"{persona_id}_*_conversation.json")
    files = sorted(_glob.glob(pattern_sub) + _glob.glob(pattern_flat))
    return Path(files[-1]) if files else None


async def run_f1_stage(ctx: ChainContext) -> StageResult:
    """Run one F1 session for `ctx.persona_id`, capture the saved conversation.json.

    Skips the live run entirely if `ctx.conversation_path` is already set
    (`--start-from-conversation`) — used for repeated F2-only iteration
    (PLAN-2026-W28-H Track C: "bug/DB setup 반복 실험 지원").
    """
    if ctx.conversation_path is not None:
        return StageResult(
            "F1", "skip",
            f"--start-from-conversation supplied — using {ctx.conversation_path.name} directly",
        )

    t0 = time.perf_counter()
    if not os.environ.get("UPSTAGE_API_KEY"):
        return StageResult(
            "F1", "fail", "UPSTAGE_API_KEY not set — cannot run PatientLLM/F1", duration_ms=_ms(t0)
        )

    try:
        from src import f1

        await f1._run_simulation(ctx.persona_id, ctx.max_turns, followup_from=None)
    except SystemExit as exc:
        return StageResult(
            "F1", "fail",
            f"F1 exited (code={exc.code}) — check persona file / API keys",
            duration_ms=_ms(t0),
        )
    except Exception as exc:  # noqa: BLE001 — harness must report, not crash, on stage failure
        logger.exception("continuous_test.f1.failed")
        return StageResult("F1", "fail", f"F1 session raised: {exc}", duration_ms=_ms(t0))

    path = _find_latest_f1_conversation(ctx.persona_id)
    if path is None:
        return StageResult(
            "F1", "fail", "F1 completed but no conversation.json was found on disk",
            duration_ms=_ms(t0),
        )
    ctx.conversation_path = path
    return StageResult(
        "F1", "pass", f"F1 session complete -> {path.name}",
        artifacts={"conversation": path}, duration_ms=_ms(t0),
    )


# ── F2 stage ────────────────────────────────────────────────────────────


def _find_latest_f2_artifact(persona_id: str, out_dir: Path | None) -> Path | None:
    from src.f1 import OUTPUT_DIR

    base = out_dir or OUTPUT_DIR
    pattern = str(base / persona_id / f"{persona_id}_*_domain_inference.json")
    files = sorted(_glob.glob(pattern))
    return Path(files[-1]) if files else None


def _read_f2_mode(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("repro", {}).get("mode", "unknown"))
    except Exception:  # noqa: BLE001 — diagnostic read, never fatal to the harness
        return "unknown"


async def run_f2_stage(ctx: ChainContext) -> StageResult:
    """Feed `ctx.conversation_path` (F1's output) into F2's `--conversation` path.

    Runs a DB preflight first and cross-checks it against F2's own reported
    `mode` — F2's Stage-1 DB/embedding failure fallback to `mode=llm_only`
    (`f2.py:183-188`) is silent by F2's own design; this stage surfaces it
    explicitly as WARN instead of letting it read as an ordinary PASS.
    """
    if ctx.conversation_path is None:
        return StageResult(
            "F2", "skip", "no F1 conversation.json available (upstream F1 stage did not succeed)"
        )

    t0 = time.perf_counter()
    db_ok, db_detail = await _db_preflight()
    preflight_note = f"db_preflight={'ok' if db_ok else 'FAILED'} ({db_detail})"

    try:
        from src import f2

        args = argparse.Namespace(
            conversation=str(ctx.conversation_path),
            persona=None,
            no_rag=False,
            k=ctx.k,
            out=str(ctx.out_dir) if ctx.out_dir else None,
            scale_scores=ctx.scale_scores_path,
            first_visit=False,
            revisit=False,
        )
        await f2._run(args)
    except SystemExit as exc:
        return StageResult(
            "F2", "fail", f"F2 exited (code={exc.code}) — {preflight_note}", duration_ms=_ms(t0)
        )
    except Exception as exc:  # noqa: BLE001 — harness must report, not crash, on stage failure
        logger.exception("continuous_test.f2.failed")
        return StageResult(
            "F2", "fail", f"F2 run raised: {exc} — {preflight_note}", duration_ms=_ms(t0)
        )

    artifact_path = _find_latest_f2_artifact(ctx.persona_id, ctx.out_dir)
    if artifact_path is None:
        return StageResult(
            "F2", "fail", f"F2 completed but no domain_inference.json was found — {preflight_note}",
            duration_ms=_ms(t0),
        )
    ctx.domain_inference_path = artifact_path
    mode = _read_f2_mode(artifact_path)

    if mode == "llm_only" and not db_ok:
        status, detail = "warn", (
            f"F2 fell back to mode=llm_only — {preflight_note}. A DB/embedding outage is "
            "reported as an ordinary completion by f2.py itself (f2.py:183-188); flagged "
            f"explicitly here -> {artifact_path.name}"
        )
    elif mode == "llm_only" and db_ok:
        status, detail = "warn", (
            f"F2 fell back to mode=llm_only ({preflight_note} — DB WAS reachable, so this is "
            f"likely empty chief_complaint/HPI slots or a mid-run embedding error, not a DB "
            f"outage) -> {artifact_path.name}"
        )
    else:
        status, detail = "pass", (
            f"F2 domain inference complete, mode={mode} ({preflight_note}) -> {artifact_path.name}"
        )

    return StageResult(
        "F2", status, detail, artifacts={"domain_inference": artifact_path}, duration_ms=_ms(t0)
    )


# ── Multi-session chain (PLAN-2026-W28-Q W2) ────────────────────────────


async def run_multi_session_chain(
    persona_id: str,
    *,
    n_sessions: int,
    max_turns: int,
    k: int,
    out_dir: Path | None,
    scale_scores_path: str | None,
    session_interval_days: int = DEFAULT_SESSION_INTERVAL_DAYS,
    base_date: date | None = None,
) -> list[StageResult]:
    """Chain N F1 sessions via the existing PUBLIC `followup_from` seam
    (`f1._run_simulation(..., followup_from=<prior session's own
    conversation.json path>)`) — session N+1 follows up from session N's
    OWN saved artifact, not a "latest for persona" glob lookup (avoids a
    race with unrelated concurrent runs for the same persona). Runs F2
    after each F1 session and appends one entry to the per-VP session
    ledger (harness artifact only — `_ledger_path`/`_append_ledger_entry`
    above; production code never reads it, REV-022 standing rule).

    A hard F1 failure halts the chain at that session (mirrors
    `run_chain`'s own halt-on-fail discipline) — sessions already completed
    keep their StageResults and ledger entries.
    """
    from src import f1
    from src.grounding import QUESTIONABLE_SLOT_KEYS

    all_results: list[StageResult] = []
    prev_conversation_path: Path | None = None
    resolved_base_date = base_date or datetime.now().date()
    ledger_path = _ledger_path(persona_id, out_dir)

    for session_index in range(1, n_sessions + 1):
        simulated_date = (
            resolved_base_date + timedelta(days=session_interval_days * (session_index - 1))
        ).isoformat()
        followup_from = str(prev_conversation_path) if prev_conversation_path else None

        t0 = time.perf_counter()
        try:
            f1_result = await f1._run_simulation(
                persona_id, max_turns, followup_from=followup_from,
                session_index=session_index, simulated_date=simulated_date,
            )
        except SystemExit as exc:
            all_results.append(StageResult(
                f"F1[session={session_index}]", "fail",
                f"F1 exited (code={exc.code}) — check persona file / API keys",
                duration_ms=_ms(t0),
            ))
            break
        except Exception as exc:  # noqa: BLE001 — harness must report, not crash
            logger.exception("continuous_test.multi_session.f1.failed")
            all_results.append(StageResult(
                f"F1[session={session_index}]", "fail", f"F1 session raised: {exc}",
                duration_ms=_ms(t0),
            ))
            break

        conv_path = _find_latest_f1_conversation(persona_id)
        if conv_path is None:
            all_results.append(StageResult(
                f"F1[session={session_index}]", "fail",
                "F1 completed but no conversation.json was found on disk",
                duration_ms=_ms(t0),
            ))
            break
        all_results.append(StageResult(
            f"F1[session={session_index}]", "pass",
            f"session_index={session_index} simulated_date={simulated_date} "
            f"is_revisit={session_index > 1} -> {conv_path.name}",
            artifacts={"conversation": conv_path}, duration_ms=_ms(t0),
        ))

        f2_ctx = ChainContext(
            persona_id=persona_id, max_turns=max_turns, k=k, out_dir=out_dir,
            scale_scores_path=scale_scores_path, conversation_path=conv_path,
        )
        f2_result = await run_f2_stage(f2_ctx)
        f2_result.name = f"F2[session={session_index}]"
        all_results.append(f2_result)

        final_slots = (
            {s["key"]: s["value"] for s in f1_result.final_slots} if f1_result else {}
        )
        missing_slots = [k for k in QUESTIONABLE_SLOT_KEYS if not final_slots.get(k)]
        ledger_entry: dict[str, Any] = {
            "session_index": session_index,
            "simulated_date": simulated_date,
            "is_revisit": session_index > 1,
            "final_slots": final_slots,
            "missing_slots": missing_slots,
            "repro": {
                "model": f1_result.model if f1_result else "",
                "prompt_version": f1_result.prompt_version if f1_result else "",
            },
            "conversation_path": str(conv_path),
            "domain_inference_path": (
                str(f2_ctx.domain_inference_path) if f2_ctx.domain_inference_path else None
            ),
            "written_at": datetime.now().isoformat(),
        }
        _append_ledger_entry(ledger_path, ledger_entry)

        prev_conversation_path = conv_path

    return all_results


def print_multi_session_report(persona_id: str, results: list[StageResult]) -> None:
    icon = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[SKIP]"}
    print(f"\n{'=' * 70}")
    print(f"  continuous_test — multi-session chain — persona={persona_id}")
    print(f"{'=' * 70}")
    for r in results:
        print(f"  {icon.get(r.status, '[?]')} {r.name:<14} ({r.duration_ms:>7.0f}ms)  {r.detail}")
        for label, path in r.artifacts.items():
            print(f"           {label}: {path}")
    print(f"{'=' * 70}")


# ── Unimplemented stages — explicit, logged skip stubs (never silent) ───

STAGE_REGISTRY: list[Stage] = [
    Stage("F1", True, run_f1_stage),
    Stage("F2", True, run_f2_stage),
    Stage("F3", False, None, note="F3 not yet implemented — no src/f3.py in this repo."),
    Stage("F4", False, None, note="F4 not yet implemented — no src/f4.py in this repo."),
    Stage("F5", False, None, note="F5 not yet implemented — no src/f5.py in this repo."),
    Stage("F6", False, None, note="F6 not yet implemented — no src/f6.py in this repo."),
]


# ── Chain runner ──────────────────────────────────────────────────────


async def run_chain(ctx: ChainContext, stages: list[Stage] | None = None) -> list[StageResult]:
    """Run every stage in order, always emitting exactly one `StageResult`
    per registry entry. A hard `fail` halts the chain — every stage after
    it is recorded as `skip` (its dependency did not succeed), never
    silently dropped from the report.
    """
    stages = stages if stages is not None else STAGE_REGISTRY
    results: list[StageResult] = []
    halted = False

    for stage in stages:
        if halted:
            results.append(StageResult(stage.name, "skip", "upstream stage failed — chain halted"))
            continue
        if not stage.implemented or stage.run is None:
            logger.warning("continuous_test.stage.skip — %s: %s", stage.name, stage.note)
            results.append(StageResult(stage.name, "skip", f"not implemented — {stage.note}"))
            continue

        logger.info("continuous_test.stage.start — %s", stage.name)
        result = await stage.run(ctx)
        logger.info("continuous_test.stage.done — %s status=%s", stage.name, result.status)
        results.append(result)
        if result.status == "fail":
            halted = True

    return results


def print_report(ctx: ChainContext, results: list[StageResult]) -> None:
    icon = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[SKIP]"}
    print(f"\n{'=' * 70}")
    print(f"  continuous_test — persona={ctx.persona_id}")
    print(f"{'=' * 70}")
    for r in results:
        print(f"  {icon.get(r.status, '[?]')} {r.name:<4} ({r.duration_ms:>7.0f}ms)  {r.detail}")
        for label, path in r.artifacts.items():
            print(f"           {label}: {path}")
    print(f"{'=' * 70}")


# ── CLI entry point ──────────────────────────────────────────────────


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="continuous_test — F1 -> F2 -> ... -> F6 chain validation harness (Track C)"
    )
    parser.add_argument("--persona", default="VP-001", help="VP-001 등 (F1 페르소나)")
    parser.add_argument("--max-turns", type=int, default=10, help="F1 최대 턴 수")
    parser.add_argument("--k", type=int, default=3, help="F2 Stage 1 테이블별 top-k")
    parser.add_argument("--out", default=None, help="출력 디렉터리 override (F1/F2 공용)")
    parser.add_argument(
        "--scale-scores", default=None, help="F2에 전달할 F3 척도 점수 JSON 경로 (선택)"
    )
    parser.add_argument(
        "--start-from-conversation",
        default=None,
        help=(
            "F1을 건너뛰고 기존 F1 conversation.json으로 F2부터 재실행 "
            "(반복 bug/DB-setup 실험용, PLAN-2026-W28-H Track C)"
        ),
    )
    parser.add_argument(
        "--sessions", type=int, default=1,
        help=(
            "다중 세션 체이닝 세션 개수 (PLAN-2026-W28-Q W2). 1(기본값)이면 기존 "
            "단일 세션 F1->F2 체인. >1이면 --followup-from seam으로 세션을 연쇄 "
            "실행하고 매 세션마다 F2 + per-VP session ledger 항목을 기록한다."
        ),
    )
    parser.add_argument(
        "--session-interval-days", type=int, default=DEFAULT_SESSION_INTERVAL_DAYS,
        help="세션 간 시뮬레이션 날짜 간격(일). --sessions > 1일 때만 사용.",
    )
    return parser


async def _main(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else None

    if args.sessions and args.sessions > 1:
        if args.start_from_conversation:
            print("--start-from-conversation is not supported together with --sessions > 1")
            return 1
        results = await run_multi_session_chain(
            args.persona,
            n_sessions=args.sessions,
            max_turns=args.max_turns,
            k=args.k,
            out_dir=out_dir,
            scale_scores_path=args.scale_scores,
            session_interval_days=args.session_interval_days,
        )
        print_multi_session_report(args.persona, results)
        return 0 if all(r.status != "fail" for r in results) else 1

    ctx = ChainContext(
        persona_id=args.persona,
        max_turns=args.max_turns,
        k=args.k,
        out_dir=out_dir,
        scale_scores_path=args.scale_scores,
    )
    if args.start_from_conversation:
        path = Path(args.start_from_conversation)
        if not path.exists():
            print(f"--start-from-conversation path not found: {path}")
            return 1
        ctx.conversation_path = path

    results = await run_chain(ctx)
    print_report(ctx, results)
    return 0 if all(r.status != "fail" for r in results) else 1


def main() -> int:
    parser = build_arg_parser()
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
    # Lazy import, matching this module's own light-import-at-parse-time
    # convention (module docstring).
    from src.prompts.loader import resolve_prompts_base_dir

    resolve_prompts_base_dir(PROJECT_ROOT)

    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
