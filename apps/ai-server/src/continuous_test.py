"""continuous_test.py — F1 -> F2 -> F3 -> ... -> F6 end-to-end validation harness.

PLAN-2026-W28-H Track C (F1/F2), PLAN-2026-W28-V (F3, `src.f3`, `ADR-031`/
`ADR-032`). Chains the pipeline stages that exist today: runs an F1 session
for a persona (`f1.py`, `F1Pipeline`), feeds the resulting F1
`conversation.json` into F2 (`f2.py`), then feeds F2's `domain_inference.json`
into F3 (`f3.py` — administers exactly the ONE questionnaire F2 recommended,
`ai_predicted_disease.recommended_questionnaire`). F4-F6 do not exist yet in
this repo — they are explicit, LOGGED skip stubs in `STAGE_REGISTRY` (never
silently omitted): add a `Stage(...)` entry with `implemented=True` and a
`run` coroutine the moment `fN.py` ships, and the chain picks it up
automatically.

F3's answer_fn (in-persona LLM score selection, or a deterministic
persona-table read) is constructed by THIS harness from
`tests/simulation/survey_answer_llm.py` and injected into `src.f3` — `src/
f3.py` itself makes zero LLM calls and imports nothing from `tests/`
(`--answer-mode {llm,expected}`, default `llm`).

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
up from session N's own saved `conversation.json`), running F2 then F3 after
each and appending one entry (with an `"f3"` sub-object, plan §5) to a per-VP
session ledger (`<OUTPUT_DIR>/<persona>/<persona>_session_ledger.json`) —
session ordinal, simulated date, final/missing slots, repro metadata. Session
N+1's F2 call prefers session N's OWN F3 `scale_scores.json` projection over
the static `--scale-scores` CLI arg (plan §6 item 4). The ledger is a HARNESS
ARTIFACT ONLY (`run_multi_session_chain`'s own docstring, REV-022 standing
rule) — production code (`f1.py`/`f2.py`/`f3.py`) never reads it. The
single-session (`--sessions 1`, default) path also writes one ledger entry
(plan §6 item 5 — previously a gap: `run_chain` wrote no ledger entry at all).

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
    # F3 with the deterministic expected-mode answer_fn (zero LLM):
    .venv/bin/python -m src.continuous_test --persona VP-012 --answer-mode expected
    # Forced-questionnaire mode (harness-only, PLAN-2026-W29-A step 6): F3
    # administers GAD-7 regardless of what F2 actually recommended. The
    # saved artifact + ledger "f3" sub-object both record
    # administration_mode="forced" — never natural-chain/F2-linkage evidence.
    .venv/bin/python -m src.continuous_test --persona VP-001 --force-questionnaire GAD-7
    # AUDIT-C sex-conditional threshold (REV-041 Resolution 2): defaults to
    # the persona's own Section 1 성별 row; --patient-sex overrides it:
    .venv/bin/python -m src.continuous_test --persona VP-012 --patient-sex female
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

    Trivially extensible: `scale_scores_path` was wired for F2's optional F3
    input before F3 existed; `f3_survey_path`/`f3_scale_scores_path` are set
    by the (now real) F3 stage below.
    """

    persona_id: str
    max_turns: int
    k: int
    out_dir: Path | None
    scale_scores_path: str | None
    # set by F1 (or --start-from-conversation), consumed by F2
    conversation_path: Path | None = None
    domain_inference_path: Path | None = None  # set by F2
    answer_mode: str = "llm"  # "llm" | "expected" — consumed by F3
    forced_scale: str | None = None  # harness-only F2->F3 override (PLAN-2026-W29-A step 6)
    # "male" / "female" / "unknown", or `None` (REV-041 Resolution 2): `None`
    # means "derive from the persona's own Section 1 성별 row automatically"
    # (`run_f3_stage`, via `tests.simulation.patient_llm.load_persona`); an
    # explicit value (e.g. from `--patient-sex`) always overrides that
    # derivation. Consumed by F3's AUDIT-C sex-conditional Korean threshold
    # (`src.scoring.survey_scorer._score_audit_c`) — porting the pattern
    # already implemented in `tests/simulation/factorial_driver.py:299,379`.
    patient_sex: str | None = None
    f3_survey_path: Path | None = None  # set by F3
    f3_scale_scores_path: Path | None = None  # set by F3 (only when outcome=="administered")
    f3_safety_pathway: dict[str, Any] | None = None  # set by F3 (PHQ-9 item-9 wiring, step 3)


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


# ── F3 stage (PLAN-2026-W28-V) ───────────────────────────────────────────
#
# src.f3 is the production administration engine (zero LLM calls, zero
# tests/ imports). This harness is the ONLY place that constructs an
# answer_fn from tests/simulation/ (SurveyAnswerLLM / expected_answer_fn)
# and wires it into src.f3 — the same import direction continuous_test.py
# already uses for src.f1/src.f2 (harness -> production), never reversed.


def _build_survey_answer_fn(persona_id: str, scale_name: str, answer_mode: str):
    """Construct the answer_fn for `scale_name`, per `answer_mode`. Only
    called when the outcome is actually `"administered"` — `expected_answer_fn`
    eagerly parses the persona's own score table at construction time, so
    building it for a non-administered outcome (e.g. an unpopulated scale
    with no such table) would raise for no reason.
    """
    if answer_mode == "expected":
        from tests.simulation.survey_answer_llm import expected_answer_fn

        return expected_answer_fn(persona_id, scale_name)

    from tests.simulation.patient_llm import load_persona
    from tests.simulation.survey_answer_llm import SurveyAnswerLLM

    persona = load_persona(persona_id)
    # scale_name is threaded through so SurveyAnswerLLM's anchor-aware
    # prompt (item bank v1) can also include the scale's entry-level
    # instruction/timeframe wording, not just the per-item anchors.
    return SurveyAnswerLLM(persona, scale_name=scale_name)


def _resolve_patient_sex(persona_id: str, override: str | None) -> str:
    """REV-041 Resolution 2: `override` (`ChainContext.patient_sex`, set
    from `--patient-sex` when the caller passed it explicitly) always wins
    when supplied; otherwise derive from the persona's own Section 1 성별
    row (`tests.simulation.patient_llm.load_persona`) — never silently
    defaults to "unknown" the way this harness's F3 stage previously did
    (`f3.py`'s own `patient_sex: str = "unknown"` default, unreached by any
    caller of this harness before this fix). Loading the persona here is
    cheap (a file read + regex, no LLM/DB call) and mirrors what
    `_build_survey_answer_fn`'s `llm` branch already does for the same
    persona in the same stage.
    """
    if override is not None:
        return override
    from tests.simulation.patient_llm import load_persona

    return load_persona(persona_id).patient_sex


def _route_phq9_safety_pathway(
    persona_id: str, responses: list[int], patient_sex: str = "unknown"
) -> dict[str, Any]:
    """`PLAN-2026-W29-A` step 3 (mission directive): item-9 >= 1 on a PHQ-9
    administration deterministically routes to the EXISTING safety
    machinery, `OrchestratorAgent.score_and_check_safety`
    (`src/agents/orchestrator.py:638` — a `@staticmethod`, deterministic,
    zero LLM calls, exercised today only by
    `tests/test_survey_safety_integration.py` and otherwise unwired to any
    live route).

    Wired HERE — the F3 artifact/ledger CONSUMER side (this harness) — and
    NEVER inside `src/f3.py`: `src/f3.py`'s own module docstring states
    nothing in that module calls `OrchestratorAgent.score_and_check_safety`
    or any safety route, an architectural boundary this mission does not
    change (`REV-038` §(2), "F3 artifact/ledger consumer side is acceptable
    if that is the real seam"). Calling the real, already-existing
    orchestrator method (rather than re-deriving `critical_item_positive`
    locally) is what makes this "routed to the existing pathway" instead of
    "a string in the score result" — `OrchestratorAgent.score_and_check_safety`
    itself makes zero LLM/DB calls, so f3.py's LLM-0 invariant is preserved
    by construction even though this call lives one layer up.

    Returns a dict recording whether/how the pathway fired — machine-
    checkable proof, not prose — for the ledger's `"f3"` sub-object.
    """
    from src.agents.orchestrator import OrchestratorAgent
    from src.schemas.orchestrator import SessionState

    state = SessionState(session_id=f"f3-safety-seam:{persona_id}")
    result, safety_triggered = OrchestratorAgent.score_and_check_safety(
        state, "PHQ-9", responses, patient_sex=patient_sex
    )
    return {
        "safety_pathway_invoked": True,
        "safety_triggered": safety_triggered,
        "recommended_action": result.recommended_action,
        "critical_item_positive": result.critical_item_positive,
    }


async def run_f3_stage(ctx: ChainContext) -> StageResult:
    """Read `ctx.domain_inference_path` (F2's output), resolve the
    administered/no_questionnaire_indicated/item_bank_unpopulated outcome
    (`src.f3.resolve_outcome`), administer via `src.f3.run_f3_administration`
    with an answer_fn built per `ctx.answer_mode`, and record
    `ctx.f3_survey_path`/`ctx.f3_scale_scores_path` for downstream consumers
    (the ledger, and — from session 2 onward in `run_multi_session_chain` —
    the NEXT session's F2 call).

    `ctx.forced_scale` (`PLAN-2026-W29-A` step 6, harness-only): when set,
    overrides which scale is resolved/administered instead of F2's own
    `recommended_questionnaire` — never force-picks silently, F2's actual
    recommendation is never mutated, and `src.f3.resolve_outcome`/
    `run_f3_administration` are never called with F2's recommendation in
    this branch (the forced scale IS what gets resolved/administered).

    Also performs the deterministic PHQ-9 item-9 safety-pathway routing
    (`_route_phq9_safety_pathway`, `PLAN-2026-W29-A` step 3) whenever the
    outcome is `administered` and `scale_name == "PHQ-9"` — regardless of
    natural/forced mode.

    `ctx.patient_sex` (REV-041 Resolution 2): resolved once, via
    `_resolve_patient_sex` (explicit `ctx.patient_sex` override, else the
    persona's own Section 1 성별 row) — BEFORE this fix this stage always
    called `run_f3_administration` with no `patient_sex` argument at all,
    silently defaulting to `"unknown"` for every persona (`f3.py:251`),
    which `_score_audit_c` treats identically to `"male"` (both threshold
    6). Threaded into both the F3 administration call (drives the
    Korean-primary AUDIT-C threshold) and the PHQ-9 safety-pathway call
    (for consistency within this one stage — `patient_sex` is currently
    unused by PHQ-9 scoring itself, but the two calls should never disagree
    about which sex value this session used).
    """
    if ctx.domain_inference_path is None:
        return StageResult(
            "F3", "skip",
            "no domain_inference.json available (upstream F2 stage did not succeed or did "
            "not produce an artifact)",
        )

    t0 = time.perf_counter()
    effective_patient_sex = _resolve_patient_sex(ctx.persona_id, ctx.patient_sex)
    try:
        from src import f3

        recommendation = f3.load_recommendation(ctx.domain_inference_path)
        effective_scale = ctx.forced_scale or recommendation.recommended_questionnaire
        outcome, _entry = f3.resolve_outcome(effective_scale)

        if outcome == f3.ADMINISTERED_OUTCOME:
            answer_fn = _build_survey_answer_fn(
                ctx.persona_id, effective_scale, ctx.answer_mode
            )
        else:
            async def answer_fn(item):  # pragma: no cover — never invoked, see below
                raise AssertionError(
                    "answer_fn must not be called for a non-administered F3 outcome"
                )

        result = await f3.run_f3_administration(
            domain_inference_path=ctx.domain_inference_path,
            answer_fn=answer_fn,
            patient_sex=effective_patient_sex,
            answer_mode=ctx.answer_mode,
            output_dir=ctx.out_dir,
            vp_id=ctx.persona_id,
            forced_scale=ctx.forced_scale,
        )
    except Exception as exc:  # noqa: BLE001 — harness must report, not crash, on stage failure
        logger.exception("continuous_test.f3.failed")
        return StageResult("F3", "fail", f"F3 run raised: {exc}", duration_ms=_ms(t0))

    output = result["output"]
    paths = result["paths"]
    ctx.f3_survey_path = paths.get("json")
    ctx.f3_scale_scores_path = paths.get("scale_scores")

    ctx.f3_safety_pathway = None
    if output.outcome == f3.ADMINISTERED_OUTCOME and output.scale_name == "PHQ-9":
        ctx.f3_safety_pathway = _route_phq9_safety_pathway(
            ctx.persona_id, output.responses, patient_sex=effective_patient_sex
        )

    detail = (
        f"F3 outcome={output.outcome} answer_mode={ctx.answer_mode} "
        f"administration_mode={output.administration_mode} patient_sex={effective_patient_sex}"
    )
    if output.outcome == f3.ADMINISTERED_OUTCOME and output.score_result is not None:
        detail += (
            f" scale={output.scale_name} total_score={output.score_result.total_score} "
            f"severity={output.score_result.severity} safety_referral={output.safety_referral}"
        )
        if ctx.f3_safety_pathway is not None:
            detail += f" safety_pathway_triggered={ctx.f3_safety_pathway['safety_triggered']}"
    return StageResult("F3", "pass", detail, artifacts=paths, duration_ms=_ms(t0))


def _build_f3_ledger_subobject(ctx: ChainContext) -> dict[str, Any] | None:
    """Build the `"f3"` ledger sub-object (plan §5) by reprojecting fields
    already computed and saved by `src.f3` — never re-derives scoring.
    Returns `None` (a present key with a null value, not an absent key —
    `_build_*_ledger_entry` callers always set `entry["f3"] = ...`) when the
    F3 stage never produced a survey.json this session (e.g. upstream F2
    failure — see `run_f3_stage`'s own "skip" path).

    `administration_mode` (`PLAN-2026-W29-A` step 6) and `threshold_caveat`
    (AUDIT-C and, as of `CVR-017` binding condition 1 / `REV-039` correction
    D, GAD-7 — `src.f3._SEVERITY_CAVEATS`) are reprojected straight from the
    saved artifact — every ledger record self-describes the same way the
    artifact itself does.
    `safety_pathway` is NOT on the saved artifact (it is computed one layer
    up, at this harness's own consumer seam — `_route_phq9_safety_pathway`)
    so it is read from `ctx.f3_safety_pathway` instead, set by `run_f3_stage`
    before this function is ever called for a real chain run. Defaults to
    `"natural"`/`None` respectively for a survey.json saved before this
    mission (v0-era artifacts never had these fields), so re-ingesting an
    old artifact never crashes ledger bookkeeping.
    """
    if ctx.f3_survey_path is None or not ctx.f3_survey_path.exists():
        return None
    try:
        data = json.loads(ctx.f3_survey_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — ledger bookkeeping must not crash the harness
        logger.warning("continuous_test.ledger.f3_survey_unreadable — %s", ctx.f3_survey_path)
        return None

    score_result = data.get("score_result") or {}
    return {
        "outcome": data.get("outcome"),
        "scale_name": data.get("scale_name"),
        "administration_mode": data.get("administration_mode", "natural"),
        "item_bank_version": data.get("item_bank_version"),
        "item_bank_provenance": data.get("item_bank_provenance"),
        "responses": data.get("responses"),
        "total_score": score_result.get("total_score"),
        "max_score": score_result.get("max_score"),
        "severity": score_result.get("severity"),
        "subscale_scores": score_result.get("subscale_scores"),
        "safety_referral": data.get("safety_referral", False),
        "threshold_caveat": data.get("threshold_caveat"),
        "safety_pathway": ctx.f3_safety_pathway,
        "answer_mode": data.get("answer_mode"),
        "recommendation_provenance": data.get("recommendation_provenance"),
        "survey_artifact_path": str(ctx.f3_survey_path),
        "scale_scores_path": (
            str(ctx.f3_scale_scores_path) if ctx.f3_scale_scores_path else None
        ),
        # F4 quick-dev provenance (§2.7, ADR-036 item 3) — reprojected
        # straight from the saved survey.json, same `.get(...)`-default
        # discipline as every other field above (absent on pre-F4 artifacts).
        "scenario_pack_id": data.get("scenario_pack_id"),
        "arc_mode": data.get("arc_mode"),
    }


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
    answer_mode: str = "llm",
    forced_scale: str | None = None,
    patient_sex: str | None = None,
    scenario_pack: tuple[Any, ...] | None = None,
    run_f4: bool = True,
) -> list[StageResult]:
    """Chain N F1 sessions via the existing PUBLIC `followup_from` seam
    (`f1._run_simulation(..., followup_from=<prior session's own
    conversation.json path>)`) — session N+1 follows up from session N's
    OWN saved artifact, not a "latest for persona" glob lookup (avoids a
    race with unrelated concurrent runs for the same persona). Runs F2, then
    F3, after each F1 session and appends one entry to the per-VP session
    ledger (harness artifact only — `_ledger_path`/`_append_ledger_entry`
    above; production code never reads it, REV-022 standing rule).

    Session chaining (plan §6 item 4, closes the previously-flagged-not-fixed
    gap): session N+1's F2 call prefers session N's OWN F3
    `scale_scores.json` (when session N's outcome was `"administered"`) over
    the static `scale_scores_path` CLI arg — session 1 always uses the
    static arg (there is no prior session yet); a session whose F3 outcome
    was NOT `"administered"` (no scores produced) falls back to the static
    arg for the next session too, never silently drops the F2 input.

    A hard F1 failure halts the chain at that session (mirrors
    `run_chain`'s own halt-on-fail discipline) — sessions already completed
    keep their StageResults and ledger entries.

    `scenario_pack` (`docs/ai/f4_quick_dev_plan.md` §2/§9 wave 4,
    `PLAN-2026-W29-D`): an optional ordered tuple of
    `tests.simulation.scenario_pack.ScenarioSession` — when supplied, its
    length MUST equal `n_sessions` (raises `ValueError` otherwise, fail-fast
    rather than silently truncating/padding). Each session then:
      - uses `scenario_pack[i].day_offset` for its `simulated_date` INSTEAD
        of the uniform `session_interval_days * (session_index - 1)`
        formula (variable-cadence support — weekly -> biweekly -> monthly);
      - has that session's OWN rendered guideline text
        (`tests.simulation.scenario_pack.render_scenario_guideline`)
        injected via `f1._run_simulation(scenario_guideline=...)` — ONLY
        that session's text ever reaches `persona.system_prompt`, never the
        whole arc table (isolation invariant, test-proven);
      - self-identifies via `scenario_pack_id`/`arc_mode`, threaded through
        every artifact class (§2.7).
    `scenario_pack=None` (every existing/natural caller) preserves the
    EXACT prior behavior — uniform interval, no guideline injection, no
    provenance tags.

    `run_f4` (design doc §6.3): after the LAST session in the loop, runs
    the F4 longitudinal-analysis stage ONCE (post-loop, not in-loop) over
    the VP's now-complete session ledger — a NEW invocation shape distinct
    from F1-F3's per-session stages. Defaults `True`; a caller wanting the
    F1->F2->F3 chain without triggering F4 (e.g. a deliberately partial
    run) sets it `False`. Never runs when the chain HALTED early on a hard
    F1 failure (mirrors `run_chain`'s own halt-on-fail discipline — no
    point analyzing a series that never got recorded this invocation).
    """
    from src import f1
    from src.grounding import QUESTIONABLE_SLOT_KEYS

    if scenario_pack is not None and len(scenario_pack) != n_sessions:
        raise ValueError(
            f"scenario_pack has {len(scenario_pack)} session(s) but n_sessions={n_sessions} "
            "— they must match exactly (fail-fast, never silently truncate/pad)"
        )

    all_results: list[StageResult] = []
    prev_conversation_path: Path | None = None
    prev_f3_scale_scores_path: Path | None = None
    resolved_base_date = base_date or datetime.now().date()
    ledger_path = _ledger_path(persona_id, out_dir)

    halted = False
    for session_index in range(1, n_sessions + 1):
        scenario_session = scenario_pack[session_index - 1] if scenario_pack is not None else None
        scenario_guideline: str | None = None
        scenario_pack_id: str | None = None
        scenario_arc_mode: str | None = None
        if scenario_session is not None:
            from tests.simulation.scenario_pack import render_scenario_guideline

            simulated_date = (
                resolved_base_date + timedelta(days=scenario_session.day_offset)
            ).isoformat()
            scenario_guideline = render_scenario_guideline(
                scenario_session, n_sessions, simulated_date
            )
            scenario_pack_id = scenario_session.scenario_pack_id
            scenario_arc_mode = scenario_session.arc_mode
        else:
            simulated_date = (
                resolved_base_date + timedelta(days=session_interval_days * (session_index - 1))
            ).isoformat()
        followup_from = str(prev_conversation_path) if prev_conversation_path else None

        t0 = time.perf_counter()
        try:
            f1_result = await f1._run_simulation(
                persona_id, max_turns, followup_from=followup_from,
                session_index=session_index, simulated_date=simulated_date,
                scenario_guideline=scenario_guideline,
                scenario_pack_id=scenario_pack_id, arc_mode=scenario_arc_mode,
            )
        except SystemExit as exc:
            all_results.append(StageResult(
                f"F1[session={session_index}]", "fail",
                f"F1 exited (code={exc.code}) — check persona file / API keys",
                duration_ms=_ms(t0),
            ))
            halted = True
            break
        except Exception as exc:  # noqa: BLE001 — harness must report, not crash
            logger.exception("continuous_test.multi_session.f1.failed")
            all_results.append(StageResult(
                f"F1[session={session_index}]", "fail", f"F1 session raised: {exc}",
                duration_ms=_ms(t0),
            ))
            halted = True
            break

        conv_path = _find_latest_f1_conversation(persona_id)
        if conv_path is None:
            all_results.append(StageResult(
                f"F1[session={session_index}]", "fail",
                "F1 completed but no conversation.json was found on disk",
                duration_ms=_ms(t0),
            ))
            halted = True
            break
        all_results.append(StageResult(
            f"F1[session={session_index}]", "pass",
            f"session_index={session_index} simulated_date={simulated_date} "
            f"is_revisit={session_index > 1} -> {conv_path.name}",
            artifacts={"conversation": conv_path}, duration_ms=_ms(t0),
        ))

        # Plan §6 item 4: session N+1 prefers session N's OWN F3 scale_scores
        # projection over the static CLI arg (session 1 has no prior session,
        # so it always uses the static arg).
        effective_scale_scores_path = (
            str(prev_f3_scale_scores_path) if prev_f3_scale_scores_path is not None
            else scale_scores_path
        )
        f2_ctx = ChainContext(
            persona_id=persona_id, max_turns=max_turns, k=k, out_dir=out_dir,
            scale_scores_path=effective_scale_scores_path, conversation_path=conv_path,
            answer_mode=answer_mode, forced_scale=forced_scale, patient_sex=patient_sex,
        )
        f2_result = await run_f2_stage(f2_ctx)
        f2_result.name = f"F2[session={session_index}]"
        all_results.append(f2_result)

        f3_result = await run_f3_stage(f2_ctx)
        f3_result.name = f"F3[session={session_index}]"
        all_results.append(f3_result)
        # Chained forward to session_index+1's F2 call above (None when this
        # session's F3 outcome wasn't "administered" — the next session then
        # falls back to the static scale_scores_path arg, never silently
        # drops the F2 input).
        prev_f3_scale_scores_path = f2_ctx.f3_scale_scores_path

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
            "f3": _build_f3_ledger_subobject(f2_ctx),
            # F4 quick-dev provenance (§2.7) — read straight off the
            # F1Result, never re-derived/guessed (`None`/absent for a
            # natural, non-scripted session, same as every f1_result-sourced
            # field above).
            "scenario_pack_id": f1_result.scenario_pack_id if f1_result else None,
            "arc_mode": f1_result.arc_mode if f1_result else None,
            "written_at": datetime.now().isoformat(),
        }
        _append_ledger_entry(ledger_path, ledger_entry)

        prev_conversation_path = conv_path

    if run_f4 and not halted:
        f4_result = await _run_f4_analysis(persona_id, out_dir)
        all_results.append(f4_result)

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


# ── F4 stage (PLAN-2026-W29-D) ───────────────────────────────────────────
#
# F4 is NOT per-session (design doc §6.3) — it runs ONCE, over a VP's
# now-complete session ledger, reading `conversation_path`/
# `domain_inference_path` pointers + the ledger's own reprojected `"f3"`
# sub-object. `src.f4.analyze_longitudinal_series` itself never touches any
# of these files — building the explicit `SessionRecord`s below IS the
# harness-side input-assembly the production/harness split requires
# (design doc §4, REV-044 Criterion 6).


def _build_session_record(entry: dict[str, Any]) -> Any | None:
    """One `src.f4.SessionRecord` per ledger entry — reads the entry's own
    `conversation_path`/`domain_inference_path` pointers (never re-derives
    them) plus the ledger's already-reprojected `"f3"` sub-object. Returns
    `None` (never raises) when the entry's own `conversation_path` is
    missing/unreadable — a corrupt/partial entry is skipped honestly, never
    fabricated.
    """
    from src.f4 import SessionRecord

    conv_path_str = entry.get("conversation_path")
    if not conv_path_str:
        return None
    conv_path = Path(conv_path_str)
    if not conv_path.exists():
        logger.warning("continuous_test.f4.conversation_unreadable — %s", conv_path)
        return None
    try:
        conv = json.loads(conv_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a corrupt artifact must not crash F4 assembly
        logger.warning("continuous_test.f4.conversation_unparseable — %s", conv_path)
        return None

    domain_candidates: list[dict[str, Any]] = []
    ai_predicted_disease: dict[str, Any] | None = None
    di_path_str = entry.get("domain_inference_path")
    if di_path_str:
        di_path = Path(di_path_str)
        if di_path.exists():
            try:
                di = json.loads(di_path.read_text(encoding="utf-8"))
                domain_candidates = di.get("domain_candidates", [])
                ai_predicted_disease = di.get("ai_predicted_disease")
            except Exception:  # noqa: BLE001 — same discipline as above
                logger.warning("continuous_test.f4.domain_inference_unparseable — %s", di_path)

    turns = conv.get("turns", [])
    turn_polarities = [
        t["sentiment"]["polarity"]
        for t in turns
        if isinstance(t.get("sentiment"), dict) and t["sentiment"].get("polarity") is not None
    ]
    turn_risk_signal_count = sum(
        1
        for t in turns
        if isinstance(t.get("sentiment"), dict) and t["sentiment"].get("risk_signal")
    )

    return SessionRecord(
        session_index=entry["session_index"],
        simulated_date=entry["simulated_date"],
        scenario_pack_id=entry.get("scenario_pack_id"),
        arc_mode=entry.get("arc_mode"),
        final_slots=entry.get("final_slots", {}),
        missing_slots=entry.get("missing_slots", []),
        session_ctrs=conv.get("session_ctrs"),
        crisis_triggered=bool(conv.get("crisis_triggered", False)),
        crisis_turn=conv.get("crisis_turn"),
        probe_events=conv.get("probe_events", []),
        risk_floor=conv.get("risk_floor"),
        turn_sentiment_polarities=turn_polarities,
        turn_risk_signal_count=turn_risk_signal_count,
        session_sentiment_summary=conv.get("session_sentiment") or None,
        domain_candidates=domain_candidates,
        ai_predicted_disease=ai_predicted_disease,
        f3=entry.get("f3"),
    )


async def _run_f4_analysis(persona_id: str, out_dir: Path | None) -> StageResult:
    """Read the VP's session ledger, assemble `SessionRecord`s, call
    `src.f4.analyze_longitudinal_series`, save via
    `src.services.f4_report.save_f4_result`. Shared by `run_f4_stage`
    (STAGE_REGISTRY, single-session path) and `run_multi_session_chain`'s
    own post-loop step — same assembly logic, never duplicated.
    """
    from src import f4
    from src.services import f4_report

    t0 = time.perf_counter()
    ledger_path = _ledger_path(persona_id, out_dir)
    entries = _load_ledger(ledger_path)
    if len(entries) < 2:
        return StageResult(
            "F4", "skip",
            f"F4 needs >=2 ledger entries for {persona_id} (got {len(entries)}) — "
            "trend analysis has nothing to compare yet",
            duration_ms=_ms(t0),
        )

    records = [r for r in (_build_session_record(e) for e in entries) if r is not None]
    if len(records) < 2:
        return StageResult(
            "F4", "warn",
            f"only {len(records)}/{len(entries)} ledger entries had readable artifacts "
            "— F4 needs >=2 to run",
            duration_ms=_ms(t0),
        )
    records.sort(key=lambda r: r.session_index)

    series_input = f4.LongitudinalSeriesInput(vp_id=persona_id, sessions=tuple(records))
    try:
        output = f4.analyze_longitudinal_series(series_input)
    except Exception as exc:  # noqa: BLE001 — harness must report, not crash, on stage failure
        logger.exception("continuous_test.f4.failed")
        return StageResult("F4", "fail", f"F4 analysis raised: {exc}", duration_ms=_ms(t0))

    paths = f4_report.save_f4_result(output, out_dir, vp_id=persona_id)
    detail = (
        f"F4 longitudinal analysis complete: n_sessions={output.n_sessions} "
        f"overall_direction={output.overall_direction} course_shape={output.course_shape} "
        f"concordance_flag={output.concordance_flag} -> {paths['json'].name}"
    )
    if output.crisis_f3_gaps:
        detail += f" | crisis_f3_gaps={len(output.crisis_f3_gaps)}"
    return StageResult("F4", "pass", detail, artifacts=paths, duration_ms=_ms(t0))


async def run_f4_stage(ctx: ChainContext) -> StageResult:
    """STAGE_REGISTRY entry point (single-session `run_chain` path) — reads
    whatever ledger entries have accumulated for `ctx.persona_id` across
    however many separate invocations (not per-invocation-only), same
    honest "skip if <2 entries" discipline as `_run_f4_analysis`."""
    return await _run_f4_analysis(ctx.persona_id, ctx.out_dir)


# ── Unimplemented stages — explicit, logged skip stubs (never silent) ───

STAGE_REGISTRY: list[Stage] = [
    Stage("F1", True, run_f1_stage),
    Stage("F2", True, run_f2_stage),
    Stage("F3", True, run_f3_stage),
    Stage("F4", True, run_f4_stage),
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
    # Lazy import — module's own light-import-at-parse-time convention.
    from src.scoring.survey_scorer import SUPPORTED_SCALES

    parser = argparse.ArgumentParser(
        description="continuous_test — F1 -> F2 -> F3 -> ... -> F6 chain validation harness"
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
    parser.add_argument(
        "--answer-mode", choices=["llm", "expected"], default="llm",
        help=(
            "F3 설문 응답 선택 모드 (PLAN-2026-W28-V §7). llm(기본값): K-EXAONE 기반 "
            "in-persona 문항별 점수 선택. expected: persona 문서의 예상 점수표 기반, "
            "LLM 미호출 결정론적 응답."
        ),
    )
    parser.add_argument(
        "--force-questionnaire",
        default=None,
        choices=sorted(SUPPORTED_SCALES),
        help=(
            "하니스 전용: F2->F3 경계에서 F2의 recommended_questionnaire와 무관하게 "
            "지정한 척도를 강제로 투여 (PLAN-2026-W29-A step 6, ADR-033 결정 6). "
            "production src/f2.py, src/f3.py의 동작은 변경되지 않음 — F3 산출물의 "
            "administration_mode 필드가 'forced'로 기록되고, ledger 'f3' 서브오브젝트도 "
            "동일하게 자기기술적으로 표시됨. 자연 선택(natural) 근거가 아니므로 "
            "F2-연계(F2-linkage) 근거로 인용하면 안 됨."
        ),
    )
    parser.add_argument(
        "--patient-sex",
        default=None,
        choices=["male", "female", "unknown"],
        help=(
            "F3 AUDIT-C의 성별-조건부 Korean-primary threshold(male/unknown>=6, "
            "female>=5)에 사용할 patient_sex를 명시적으로 override (REV-041 Resolution "
            "2). 기본값(미지정)은 페르소나 문서 Section 1의 '성별' 행에서 자동 유도 "
            "('남성'->male, '여성'->female, 그 외/누락->unknown) — "
            "tests/simulation/factorial_driver.py --patient-sex와 동일한 값 도메인."
        ),
    )
    parser.add_argument(
        "--scenario-pack",
        default=None,
        choices=["VP-001", "VP-003"],
        help=(
            "F4 quick-dev (PLAN-2026-W29-D): tests/simulation/scenario_pack.py의 "
            "해당 VP 11-세션 스크립트를 로드해 --sessions 체인에 threading한다 "
            "(--sessions > 1 필수 조합). 지정 시 --sessions/--session-interval-days는 "
            "무시되고 팩 고유의 세션 수/day_offset 스케줄이 사용된다 — 팩이 없는 "
            "자연(natural) 세션은 이 플래그를 절대 지정하지 않는다."
        ),
    )
    parser.add_argument(
        "--no-f4",
        action="store_true",
        help=(
            "다중 세션 체인(--sessions > 1) 완료 후 자동으로 실행되는 F4 종단 분석 "
            "post-loop 단계를 건너뛴다 (기본값: F4 실행)."
        ),
    )
    return parser


def _build_single_session_ledger_entry(
    ctx: ChainContext, results: list[StageResult]
) -> dict[str, Any]:
    """Build one ledger entry for the single-session (`--sessions 1`
    default) path, mirroring `run_multi_session_chain`'s entry shape
    (`session_index=1`, `is_revisit=False`) — closes the plan §6 item 5
    single-session ledger gap (`run_chain` previously wrote no ledger entry
    at all).
    """
    from src.grounding import QUESTIONABLE_SLOT_KEYS

    final_slots: dict[str, str] = {}
    model = ""
    prompt_version = ""
    scenario_pack_id: str | None = None
    arc_mode: str | None = None
    if ctx.conversation_path is not None and ctx.conversation_path.exists():
        try:
            data = json.loads(ctx.conversation_path.read_text(encoding="utf-8"))
            final_slots = {
                s["key"]: s["value"] for s in data.get("final_slots", []) if s.get("value")
            }
            model = data.get("model", "")
            prompt_version = data.get("prompt_version", "")
            scenario_pack_id = data.get("scenario_pack_id")
            arc_mode = data.get("arc_mode")
        except Exception:  # noqa: BLE001 — ledger bookkeeping must not crash the harness
            logger.warning(
                "continuous_test.ledger.conversation_unreadable — %s", ctx.conversation_path
            )
    missing_slots = [k for k in QUESTIONABLE_SLOT_KEYS if not final_slots.get(k)]

    return {
        "session_index": 1,
        "simulated_date": datetime.now().date().isoformat(),
        "is_revisit": False,
        "final_slots": final_slots,
        "missing_slots": missing_slots,
        "repro": {"model": model, "prompt_version": prompt_version},
        "conversation_path": str(ctx.conversation_path) if ctx.conversation_path else None,
        "domain_inference_path": (
            str(ctx.domain_inference_path) if ctx.domain_inference_path else None
        ),
        "f3": _build_f3_ledger_subobject(ctx),
        # F4 quick-dev provenance (§2.7) — reprojected from the saved
        # conversation.json, `None`/absent for a natural session.
        "scenario_pack_id": scenario_pack_id,
        "arc_mode": arc_mode,
        "written_at": datetime.now().isoformat(),
    }


async def _main(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else None
    answer_mode = getattr(args, "answer_mode", "llm") or "llm"
    forced_scale = getattr(args, "force_questionnaire", None)
    patient_sex = getattr(args, "patient_sex", None)
    scenario_pack_name = getattr(args, "scenario_pack", None)
    run_f4 = not getattr(args, "no_f4", False)

    scenario_pack = None
    n_sessions = args.sessions
    if scenario_pack_name:
        from tests.simulation.scenario_pack import get_scenario_pack

        scenario_pack = get_scenario_pack(scenario_pack_name)
        n_sessions = len(scenario_pack)
        print(
            f"[F4 scenario-pack] Loaded {scenario_pack_name} ({n_sessions} sessions) — "
            f"overriding --sessions={args.sessions} -> {n_sessions}"
        )

    if n_sessions and n_sessions > 1:
        if args.start_from_conversation:
            print("--start-from-conversation is not supported together with --sessions > 1")
            return 1
        results = await run_multi_session_chain(
            args.persona,
            n_sessions=n_sessions,
            max_turns=args.max_turns,
            k=args.k,
            out_dir=out_dir,
            scale_scores_path=args.scale_scores,
            session_interval_days=args.session_interval_days,
            answer_mode=answer_mode,
            forced_scale=forced_scale,
            patient_sex=patient_sex,
            scenario_pack=scenario_pack,
            run_f4=run_f4,
        )
        print_multi_session_report(args.persona, results)
        return 0 if all(r.status != "fail" for r in results) else 1

    ctx = ChainContext(
        persona_id=args.persona,
        max_turns=args.max_turns,
        k=args.k,
        out_dir=out_dir,
        scale_scores_path=args.scale_scores,
        answer_mode=answer_mode,
        forced_scale=forced_scale,
        patient_sex=patient_sex,
    )
    if args.start_from_conversation:
        path = Path(args.start_from_conversation)
        if not path.exists():
            print(f"--start-from-conversation path not found: {path}")
            return 1
        ctx.conversation_path = path

    results = await run_chain(ctx)
    print_report(ctx, results)

    # Plan §6 item 5: single-session ledger gap fix. Only written when F1
    # itself did not hard-fail (mirrors run_multi_session_chain's own
    # discipline of never writing a ledger entry for a session whose F1
    # failed) — a "skip" F1 status (--start-from-conversation) still writes.
    f1_result = next((r for r in results if r.name == "F1"), None)
    if f1_result is not None and f1_result.status != "fail":
        ledger_path = _ledger_path(args.persona, out_dir)
        _append_ledger_entry(ledger_path, _build_single_session_ledger_entry(ctx, results))

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
