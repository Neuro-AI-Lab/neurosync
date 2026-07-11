"""Smoke test — LIVE proof of `src.injection_protocol.compose_injected_patient_input_fn`.

PLAN-2026-W28-Q W3, brief item 4 ("live composer proof"). Exercises the
composer through the REAL production STT/OCR agent factories
(`src.dependencies.get_stt_agent`/`get_ocr_agent` — the SAME singletons
`f1.py` itself uses), against ONE existing fixture mp3 (SKT batch STT) and
ONE existing fixture PDF (Upstage Document Parse). EXACTLY 2 vendor calls,
ZERO model/LLM calls — no F1/F2 session runs here (that is W7's job).

Never prints full clinical/fixture text — only lengths and a 10-char
preview, per the reporting discipline this script itself must honor. Never
prints .env values.

Usage:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_injection_composer
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "apps" / "ai-server" / "tests" / "fixtures"


async def _base_fn(_agent_response: str) -> str:  # pragma: no cover - never invoked
    raise AssertionError(
        "base_fn should never be called — every turn in this proof's schedule is injected"
    )


async def main() -> int:
    load_dotenv(REPO_ROOT / "apps" / "ai-server" / ".env")

    # Import AFTER load_dotenv so ModelRouter/Settings pick up the .env.
    from src.dependencies import get_ocr_agent, get_stt_agent
    from src.injection_protocol import (
        InjectionCue,
        compose_injected_patient_input_fn,
        validate_schedule,
    )

    stt_fixture = FIXTURES_DIR / "audio" / "VP-001" / "VP-001-001.mp3"
    ocr_fixture = FIXTURES_DIR / "ocr" / "VP-001" / "VP-001_first_visit_mild_ocr.pdf"

    schedule = [
        InjectionCue(turn_index=0, modality="stt", fixture_path=stt_fixture, label="proof-stt"),
        InjectionCue(turn_index=1, modality="ocr", fixture_path=ocr_fixture, label="proof-ocr"),
    ]

    issues = validate_schedule(schedule)
    if issues:
        for issue in issues:
            print(f"[ERR] schedule invalid — turn {issue.turn_index}: {issue.reason}",
                  file=sys.stderr)
        return 1

    composed, events = compose_injected_patient_input_fn(
        _base_fn, schedule, session_id="smoke-injection-composer", patient_id="VP-001",
        get_stt_agent_fn=get_stt_agent, get_ocr_agent_fn=get_ocr_agent,
    )

    print("=== injection_protocol live composer proof — 2 vendor calls, 0 model calls ===")
    print(f"STT fixture: {stt_fixture.relative_to(REPO_ROOT)}")
    print(f"OCR fixture: {ocr_fixture.relative_to(REPO_ROOT)}")
    print()

    overall_ok = True

    # Turn 0 — STT.
    try:
        stt_text = await composed("(session opening greeting placeholder)")
        stt_ok = bool(stt_text.strip())
    except Exception as exc:  # noqa: BLE001 — report and continue to the OCR half
        print(f"[FAIL] STT half raised: {type(exc).__name__}: {exc}", file=sys.stderr)
        stt_ok = False
        overall_ok = False

    if stt_ok:
        ev = events[-1]
        print(f"[PASS] STT — vendor={ev.vendor} chars={ev.char_count} "
              f"latency_ms={ev.latency_ms:.0f} source_id={ev.source_id!r} "
              f"preview={ev.text_preview!r}")

    # Turn 1 — OCR.
    try:
        ocr_text = await composed("(agent turn 1 placeholder)")
        ocr_ok = bool(ocr_text.strip())
    except Exception as exc:  # noqa: BLE001 — report, do not retry more than once
        print(f"[FAIL] OCR half raised: {type(exc).__name__}: {exc}", file=sys.stderr)
        ocr_ok = False
        overall_ok = False

    if ocr_ok:
        ev = events[-1]
        print(f"[PASS] OCR — vendor={ev.vendor} chars={ev.char_count} "
              f"latency_ms={ev.latency_ms:.0f} source_id={ev.source_id!r} "
              f"preview={ev.text_preview!r}")

    overall_ok = overall_ok and stt_ok and ocr_ok

    print()
    print(f"Provenance events recorded: {len(events)} (expected 2)")
    for e in events:
        print(f"  turn={e.turn_index} modality={e.modality} source_id={e.source_id} "
              f"chars={e.char_count}")

    print()
    print("=== Summary ===")
    print(f"  {'PASS' if overall_ok and len(events) == 2 else 'FAIL'}")
    return 0 if (overall_ok and len(events) == 2) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
