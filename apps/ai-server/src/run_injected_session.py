"""run_injected_session.py — protocol runner: F1Pipeline + injection schedule.

`docs/ai/validation_plan_f1f2_continuous.md` §3 "STT/OCR arbitrary-turn
injection" row + §6 canary design (SC-13 persona-independence canary,
SC-15 prompt-echo probe). Part of the EXTERNAL verification-protocol layer
(`injection_protocol.py`/`continuous_test.py` lineage), not production code
— invariant 1 (plan §2): zero test-only hook, import, flag, or parameter
enters `src/f1.py` or `src/f2.py`. This module imports FROM production
(`src.f1.F1Pipeline`/`save_f1_result`, the SAME classes/functions f1.py's
own CLI uses) and from the harness layer (`tests.simulation.patient_llm`,
`src.injection_protocol`) — never the other direction; the standing AVC-03
grep (persona/harness references inside `src/agents|schemas|routes`) stays
clean.

## What this module does

Combines two EXISTING public seams into one runnable session, closing the
gap the blocked SC-13/SC-15 battery cells named: neither seam alone drives
a live F1 session with a persona loaded from an arbitrary path AND a
scheduled literal-text/STT/OCR turn.

  1. A persona source — `tests.simulation.patient_llm.load_persona`'s VP-NNN
     ID or explicit `.md` path (e.g. an audit-only
     `docs/ai/personas/_canary_audit/` copy for SC-13).
  2. An injection schedule — `src.injection_protocol.InjectionCue` list
     (JSON via `--schedule`), covering all three modalities: `"stt"`,
     `"ocr"` (real vendor-transcribed/parsed fixture content) and `"text"`
     (the cue's own literal string, no vendor call — SC-15's prompt-echo
     probes).

The composed patient responder is handed to `F1Pipeline.run_session`
through its existing PUBLIC `patient_input_fn` seam — the exact seam
`f1._run_simulation`'s own live PatientLLM wiring uses — so this runner
never adds a test-only parameter to `F1Pipeline` itself.

Output: the SAME artifact shape f1.py's own CLI produces
(`save_f1_result` — `conversation.json` + checklist + report under
`OUTPUT_DIR/<VP-ID>/`), plus the injection composer's harness-only
modality-provenance sidecar (`injection_protocol.write_provenance_sidecar`)
next to it — so downstream audits see identical artifacts to a normal
simulation run, with injection provenance tracked alongside, never inside,
the production artifact.

Usage (live):
    cd apps/ai-server
    .venv/bin/python -m src.run_injected_session --persona VP-001 \\
        --schedule path/to/schedule.json --max-turns 6
    .venv/bin/python -m src.run_injected_session \\
        --persona docs/ai/personas/_canary_audit/VP-001_first_visit_mild.md \\
        --schedule path/to/schedule.json --max-turns 6

Programmatic (also the mocked-LLM test seam — `pipeline`/`base_patient_fn`
injection points let a test drive a full in-process session with zero
vendor/model calls):
    result, artifact_paths, sidecar_path, events = await run_injected_session(
        persona_source="VP-001", schedule=schedule, max_turns=6,
    )
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.f1 import PERSONA_LOCATIONS, F1Pipeline, F1Result, save_f1_result
from src.injection_protocol import (
    InjectionCue,
    ModalityProvenanceEvent,
    PatientInputFn,
    compose_injected_patient_input_fn,
    load_schedule_from_json,
    validate_schedule,
    write_provenance_sidecar,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/run_injected_session.py -> neurosync/


def _persona_id_for_lookup(persona_source: str) -> str:
    """Best-effort VP-NNN id for `PERSONA_LOCATIONS`/session-naming purposes.

    Mirrors `tests.simulation.patient_llm.load_persona`'s own path-mode id
    derivation (the filename's leading underscore-delimited token), so a
    `_canary_audit/` path resolves to the SAME id/coordinate f1.py's own
    CLI would use for a normal ID-mode load of the same VP.
    """
    if persona_source.endswith(".md"):
        return Path(persona_source).stem.split("_", 1)[0]
    return persona_source


async def run_injected_session(
    *,
    persona_source: str,
    schedule: list[InjectionCue],
    max_turns: int = 15,
    session_id: str | None = None,
    out_dir: Path | None = None,
    patient_lat: float | None = None,
    patient_lng: float | None = None,
    pipeline: F1Pipeline | None = None,
    base_patient_fn: PatientInputFn | None = None,
) -> tuple[F1Result, dict[str, Path], Path, list[ModalityProvenanceEvent]]:
    """Drive one F1 session in-process with `schedule` injected at its
    scheduled turns, via f1.py's existing PUBLIC `patient_input_fn` seam.

    Args:
        persona_source: VP-NNN id, or an explicit `.md` path (seam 1,
            `tests.simulation.patient_llm.load_persona`).
        schedule: injection cues (seam 2, `src.injection_protocol`) —
            validated with `validate_schedule` before anything else runs;
            a failing schedule raises `ValueError` before any persona load,
            pipeline construction, or vendor/model call.
        pipeline: inject a pre-built `F1Pipeline` (e.g.
            `tests.f1_testkit.make_pipeline()`) to bypass live model-router/
            prompt-loader construction in tests. Defaults to a live
            `F1Pipeline()`, matching `f1._run_simulation`'s own wiring.
        base_patient_fn: inject a stub base responder for non-scheduled
            turns (mocked-LLM tests). Defaults to a live
            `PatientLLM(persona=...).respond`, matching
            `f1._run_simulation`'s own wiring — only constructed when this
            argument is omitted, so a fully-injected schedule under test
            never touches `PatientLLM`/vendor credentials.

    Returns:
        `(result, artifact_paths, sidecar_path, events)` — `artifact_paths`
        is `save_f1_result`'s own return value (same shape as f1.py's CLI);
        `sidecar_path` is the harness-only modality-provenance sidecar;
        `events` is the composer's own mutable event list (already fully
        populated by the time this coroutine returns).

    Raises:
        ValueError: `schedule` fails `validate_schedule` (missing fixture,
            duplicate turn_index, etc.) — never silently proceeds with a
            partially-invalid schedule.
    """
    issues = validate_schedule(schedule)
    if issues:
        detail = "; ".join(f"turn {i.turn_index}: {i.reason}" for i in issues)
        raise ValueError(f"run_injected_session: schedule failed validation — {detail}")

    persona_id = _persona_id_for_lookup(persona_source)
    resolved_session_id = session_id or f"f1_{persona_id}_injected"

    from tests.simulation.patient_llm import load_persona

    persona = load_persona(persona_source)

    if base_patient_fn is None:
        from tests.simulation.patient_llm import PatientLLM

        patient = PatientLLM(persona=persona)  # auto-loads EXAONE keys from env

        async def base_patient_fn(agent_msg: str) -> str:  # type: ignore[misc]
            return await patient.respond(agent_msg)

    composed_fn, events = compose_injected_patient_input_fn(
        base_patient_fn,
        schedule,
        session_id=resolved_session_id,
        patient_id=persona.persona_id,
    )

    resolved_lat, resolved_lng = patient_lat, patient_lng
    if resolved_lat is None or resolved_lng is None:
        default = PERSONA_LOCATIONS.get(persona_id)
        if default:
            resolved_lat, resolved_lng = default

    active_pipeline = pipeline or F1Pipeline()
    result = await active_pipeline.run_session(
        patient_input_fn=composed_fn,
        session_id=resolved_session_id,
        persona_id=persona.persona_id,
        persona_name=persona.name,
        max_turns=max_turns,
        patient_lat=resolved_lat,
        patient_lng=resolved_lng,
    )

    artifact_paths = save_f1_result(result, output_dir=out_dir)
    sidecar_path = write_provenance_sidecar(
        artifact_paths["json"], events, persona_id=persona.persona_id,
    )
    return result, artifact_paths, sidecar_path, events


# ── CLI entry point ──────────────────────────────────────────────────


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "run_injected_session — drive one F1 session in-process with an "
            "STT/OCR/text injection schedule "
            "(validation_plan_f1f2_continuous.md §3/§6, SC-13/SC-15 execution vehicle)"
        )
    )
    parser.add_argument(
        "--persona", required=True,
        help="VP-NNN persona ID, or an explicit .md path (e.g. a _canary_audit/ copy)",
    )
    parser.add_argument(
        "--schedule", required=True, help="Path to an injection schedule JSON file",
    )
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--out", default=None, help="Output directory override")
    return parser


async def _main(args: argparse.Namespace) -> int:
    schedule = load_schedule_from_json(Path(args.schedule))
    issues = validate_schedule(schedule)
    if issues:
        for issue in issues:
            print(f"[ERR] schedule invalid — turn {issue.turn_index}: {issue.reason}",
                  file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else None
    result, paths, sidecar_path, events = await run_injected_session(
        persona_source=args.persona,
        schedule=schedule,
        max_turns=args.max_turns,
        session_id=args.session_id,
        out_dir=out_dir,
    )

    print(f"\n{'=' * 60}")
    print(f"  Injected session complete — persona={result.persona_id}")
    print(f"{'=' * 60}")
    print(f"  Turns: {result.total_turns}")
    print(f"  Crisis: {f'YES (turn {result.crisis_turn})' if result.crisis_triggered else 'No'}")
    print(f"  Injected events: {len(events)}")
    for e in events:
        print(f"    turn={e.turn_index} modality={e.modality} source_id={e.source_id} "
              f"chars={e.char_count}")
    print(f"  Files: {', '.join(p.name for p in paths.values())}, {sidecar_path.name}")
    print(f"{'=' * 60}")
    return 0


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

    # BUG-021: fail-fast path-existence validation before any live agent call
    # (matches continuous_test.py's own main() convention).
    from src.prompts.loader import resolve_prompts_base_dir

    resolve_prompts_base_dir(PROJECT_ROOT)

    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
