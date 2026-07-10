"""Verification — feed STT-transcribed patient text back into F1 pipeline.

Goal (사용자 요청): "STT 결과로 F1 파이프라인 재실행 → 원본 텍스트 대화와 동일한
결과 나오는지 확인"

Approach:
- Load STT smoke test results (VP-001_stt_smoke_results.json)
- Substitute #5 with expected text (STT file was corrupt — see VP-001_stt_smoke_results)
- Provide a canned patient_input_fn that returns transcribed text in sequence
- Run F1Pipeline with the same session config as VP-001_20260708_140746
- Compare slots, CTRS, coverage, crisis with original

Run:
    cd apps/ai-server
    .venv/bin/python -m tests.verify_stt_to_f1
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

# Set prompts dir BEFORE importing f1 (PromptLoader is instantiated as singleton)
os.environ.setdefault(
    "PROMPTS_BASE_DIR",
    str(REPO_ROOT / "docs" / "ai" / "prompts"),
)
VP_DIR = REPO_ROOT / "docs" / "ai" / "simulation_results" / "VP-001"
STT_RESULTS = VP_DIR / "VP-001_stt_smoke_results.json"
ORIGINAL_TEXT_RUN = VP_DIR / "VP-001_20260708_140746_conversation.json"
TTS_INDEX = (
    REPO_ROOT / "docs" / "ai" / "simulation_results" / "tts_scripts" / "patient_tts_index.json"
)

logger = logging.getLogger(__name__)


def load_stt_transcripts() -> list[str]:
    """Load 7 STT transcripts, substitute #5 (corrupt) with expected text from TTS index."""
    stt_data = json.loads(STT_RESULTS.read_text(encoding="utf-8"))
    stt_by_idx = {r["utterance_index"]: r["hypothesis"] for r in stt_data}

    tts_idx = json.loads(TTS_INDEX.read_text(encoding="utf-8"))
    expected_by_idx = {
        u["utterance_index"]: u["full"]
        for u in tts_idx["personas"]["VP-001"]["utterances"]
    }

    # For #5, use expected text (STT file was corrupt — same as #4 audio)
    ordered: list[str] = []
    for i in range(1, 8):
        stt_text = stt_by_idx.get(i, "").strip()
        expected = expected_by_idx.get(i, "").strip()

        # Detect the corrupt case: STT #5 == STT #4 (same audio)
        if i == 5 and stt_by_idx.get(5) == stt_by_idx.get(4):
            logger.warning(
                "Utterance #%d: STT input was corrupt (matched #4), substituting expected text",
                i,
            )
            ordered.append(expected)
        elif not stt_text:
            ordered.append(expected)
        else:
            ordered.append(stt_text)
    return ordered


def make_patient_fn(transcripts: list[str]):
    """Build an async callback that returns transcripts in order.

    F1Pipeline calls this with the agent_response each turn. We ignore what the
    AI asked and just return the next canned STT text. This deliberately mimics
    the ORIGINAL run's patient turns so we can compare downstream.

    Raises StopIteration when transcripts are exhausted (F1 will record error).
    """
    idx = {"i": 0}

    async def _fn(agent_response: str) -> str:
        i = idx["i"]
        if i >= len(transcripts):
            raise RuntimeError(f"Ran out of STT transcripts after {i} turns")
        idx["i"] += 1
        return transcripts[i]

    return _fn


def compare_runs(original: dict, replay: dict) -> dict:
    """Compare slot/CTRS/coverage/crisis between the two runs."""
    orig_slots = {s["key"]: s["value"] for s in original.get("final_slots", [])}
    rep_slots = {s["key"]: s["value"] for s in replay.get("final_slots", [])}

    all_keys = sorted(set(orig_slots) | set(rep_slots))
    slot_diff = []
    slot_matches = 0
    for k in all_keys:
        o = orig_slots.get(k, "")
        r = rep_slots.get(k, "")
        match = bool(o) == bool(r)  # 둘 다 채워졌거나 둘 다 비었는지 (existence match)
        if match:
            slot_matches += 1
        slot_diff.append({"slot": k, "original": o, "replay": r, "existence_match": match})

    return {
        "original_turns": original.get("total_turns"),
        "replay_turns": replay.get("total_turns"),
        "original_crisis": original.get("crisis_triggered"),
        "replay_crisis": replay.get("crisis_triggered"),
        "original_coverage": original.get("slot_coverage"),
        "replay_coverage": replay.get("slot_coverage"),
        "original_grounded": original.get("grounded_coverage"),
        "replay_grounded": replay.get("grounded_coverage"),
        "original_ctrs_min": original.get("session_ctrs"),
        "replay_ctrs_min": replay.get("session_ctrs"),
        "slot_existence_match": f"{slot_matches}/{len(all_keys)}",
        "slot_diff": slot_diff,
        "original_errors": len(original.get("errors", [])),
        "replay_errors": len(replay.get("errors", [])),
    }


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    load_dotenv(REPO_ROOT / "apps" / "ai-server" / ".env")

    # Import here so env is loaded first
    from src.f1 import F1Pipeline, save_f1_result

    # Load original for comparison
    original = json.loads(ORIGINAL_TEXT_RUN.read_text(encoding="utf-8"))
    print("=== STT → F1 재현 검증 (VP-001) ===")
    print(f"Original run: {ORIGINAL_TEXT_RUN.name}")
    print(f"  turns={original['total_turns']} crisis={original['crisis_triggered']} "
          f"coverage={original['slot_coverage']:.0%}")
    print()

    # Load STT transcripts
    transcripts = load_stt_transcripts()
    print(f"STT transcripts ({len(transcripts)}):")
    for i, t in enumerate(transcripts, 1):
        print(f"  #{i}: {t[:90]}")
    print()

    # Run F1 with canned patient callback
    patient_fn = make_patient_fn(transcripts)
    pipeline = F1Pipeline()
    result = await pipeline.run_session(
        patient_input_fn=patient_fn,
        session_id="f1_VP-001_stt_replay",
        persona_id="VP-001",
        persona_name="김서연",
        max_turns=len(transcripts) + 2,  # small headroom
        # Note: no OCR here — plain STT-replay comparison
    )

    # Save
    paths = save_f1_result(result, output_dir=REPO_ROOT / "docs" / "ai" / "simulation_results")
    print()
    print("=== Replay result ===")
    print(f"  turns={result.total_turns} crisis={result.crisis_triggered} "
          f"coverage={result.slot_coverage:.0%} grounded={result.grounded_coverage:.0%} "
          f"errors={len(result.errors)}")
    print(f"  saved: {[p.name for p in paths.values()]}")

    # Compare
    replay = json.loads(paths["json"].read_text(encoding="utf-8"))
    diff = compare_runs(original, replay)
    print()
    print("=== 비교: 원본 텍스트 vs STT 재현 ===")
    print(f"  turns:       original={diff['original_turns']} vs replay={diff['replay_turns']}")
    print(f"  crisis:      original={diff['original_crisis']} vs replay={diff['replay_crisis']}")
    print(
        f"  coverage:    original={diff['original_coverage']:.0%} "
        f"vs replay={diff['replay_coverage']:.0%}"
    )
    print(
        f"  grounded:    original={diff['original_grounded']:.0%} "
        f"vs replay={diff['replay_grounded']:.0%}"
    )
    print(
        f"  session_ctrs: original={diff['original_ctrs_min']} "
        f"vs replay={diff['replay_ctrs_min']}"
    )
    print(f"  slot existence match: {diff['slot_existence_match']}")
    print(f"  errors:      original={diff['original_errors']} vs replay={diff['replay_errors']}")
    print()
    print("Slot-by-slot:")
    for s in diff["slot_diff"]:
        tag = "✓" if s["existence_match"] else "✗"
        o = (s["original"] or "")[:60] or "(empty)"
        r = (s["replay"] or "")[:60] or "(empty)"
        print(f"  {tag} {s['slot']}:")
        print(f"      원본: {o}")
        print(f"      재현: {r}")

    # Save diff
    diff_path = VP_DIR / "VP-001_stt_replay_diff.json"
    diff_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  diff saved: {diff_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
