"""Grounding audit tool (T1-F1-VER-014) — replay a saved F1 conversation.json.

Re-evaluates every final slot value of a saved F1 session against the patient
utterances using the SAME grounding filter as the runtime pipeline
(src/grounding.py), so runtime and audit always agree.

Works on OLD runs too: patient utterances and per-turn AI questions are
derived from the turns array. Old runs have no `targeted_slot` info, so
negative-template values without ask evidence are reported as ungrounded
(deliberately strict — that is exactly the 2026-07-03 fabrication pattern).

Usage:
    cd apps/ai-server
    .venv/bin/python -m src.eval.grounding_audit path/to/xxx_conversation.json
    .venv/bin/python -m src.eval.grounding_audit xxx_conversation.json --out out_dir

Outputs:
    {out}/{input_stem}_grounding_audit.json
    {out}/{input_stem}_grounding_audit.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.grounding import (
    QUESTIONABLE_SLOT_KEYS,
    RISK_SLOT_KEY,
    VERDICT_GROUNDED,
    VERDICT_NEGATIVE_GROUNDED,
    VERDICT_SYSTEM_SLOT,
    VERDICT_UNGROUNDED,
    evaluate_slot_grounding,
)

_ALL_VERDICTS = (
    VERDICT_GROUNDED,
    VERDICT_NEGATIVE_GROUNDED,
    VERDICT_SYSTEM_SLOT,
    VERDICT_UNGROUNDED,
)


def extract_utterances_and_asked(
    data: dict[str, Any],
) -> tuple[list[str], list[str | None]]:
    """Derive patient utterances + aligned asked-slot info from the turns array.

    - Consecutive duplicate patient messages are collapsed (the F1 pipeline
      records the first patient message on both turn 0 and turn 1).
    - Utterance i answers the AI question of the PREVIOUS turn; the opening
      greeting targets chief_complaint. Old runs without `targeted_slot`
      yield None (unknown) entries.
    """
    turns = sorted(data.get("turns", []), key=lambda t: t.get("turn", 0))
    utterances: list[str] = []
    asked: list[str | None] = []

    prev_targeted: str | None = "chief_complaint"  # opening greeting target
    last_msg: str | None = None
    for t in turns:
        msg = t.get("patient_message", "") or ""
        if msg and msg != last_msg:
            utterances.append(msg)
            asked.append(prev_targeted)
            last_msg = msg
        prev_targeted = t.get("targeted_slot")
    return utterances, asked


def _risk_written_by_probe(data: dict[str, Any]) -> bool:
    """True when the (new-format) session wrote risk_assessment via the probe."""
    return any(
        e.get("risk_assessment_written") for e in data.get("probe_events", [])
    )


def audit_conversation(data: dict[str, Any]) -> dict[str, Any]:
    """Audit all final slot values of a saved F1 conversation dict."""
    utterances, asked = extract_utterances_and_asked(data)

    slots: list[dict[str, Any]] = []
    counts: dict[str, int] = {v: 0 for v in _ALL_VERDICTS}

    probe_grounded_risk = _risk_written_by_probe(data)

    for slot in data.get("final_slots", []):
        key = slot.get("key", "")
        value = slot.get("value", "") or ""

        if key == RISK_SLOT_KEY and probe_grounded_risk:
            verdict_name = VERDICT_GROUNDED
            reason = "populated by the safety probe protocol (probe_events)"
        else:
            verdict = evaluate_slot_grounding(key, value, utterances, asked)
            verdict_name = verdict.verdict
            reason = verdict.reason

        counts[verdict_name] = counts.get(verdict_name, 0) + 1
        slots.append({
            "key": key,
            "value": value,
            "verdict": verdict_name,
            "reason": reason,
        })

    accepted_questionable = {
        s["key"]
        for s in slots
        if s["key"] in QUESTIONABLE_SLOT_KEYS
        and s["verdict"] in (VERDICT_GROUNDED, VERDICT_NEGATIVE_GROUNDED)
    }
    recomputed_coverage = len(accepted_questionable) / len(QUESTIONABLE_SLOT_KEYS)

    return {
        "session_id": data.get("session_id"),
        "persona_id": data.get("persona_id"),
        "total_turns": data.get("total_turns", 0),
        "n_patient_utterances": len(utterances),
        "reported_slot_coverage": data.get("slot_coverage", 0),
        "reported_grounded_coverage": data.get("grounded_coverage"),
        "recomputed_grounded_coverage": round(recomputed_coverage, 4),
        "counts": counts,
        "slots": slots,
    }


def _build_markdown(audit: dict[str, Any], source: str) -> str:
    counts = audit["counts"]
    lines = [
        f"# Grounding Audit — {audit.get('persona_id') or audit.get('session_id')}",
        "",
        f"> Source: {source}",
        f"> Turns: {audit['total_turns']} | Patient utterances: {audit['n_patient_utterances']}",
        f"> Reported coverage: {audit['reported_slot_coverage']} (legacy) / "
        f"{audit['reported_grounded_coverage']} (grounded)",
        f"> Recomputed grounded coverage: {audit['recomputed_grounded_coverage']}",
        "",
        "## Verdict counts",
        "",
        "| Verdict | Count |",
        "|---|---|",
        f"| grounded | {counts.get(VERDICT_GROUNDED, 0)} |",
        f"| negative_grounded | {counts.get(VERDICT_NEGATIVE_GROUNDED, 0)} |",
        f"| ungrounded | {counts.get(VERDICT_UNGROUNDED, 0)} |",
        f"| system_slot | {counts.get(VERDICT_SYSTEM_SLOT, 0)} |",
        "",
        "## Per-slot verdicts",
        "",
        "| Slot | Verdict | Value | Reason |",
        "|---|---|---|---|",
    ]
    for s in audit["slots"]:
        value = s["value"].replace("|", "\\|")
        if len(value) > 80:
            value = value[:80] + "..."
        reason = s["reason"].replace("|", "\\|")
        lines.append(f"| {s['key']} | **{s['verdict']}** | {value} | {reason} |")
    lines.append("")
    return "\n".join(lines)


def audit_file(conversation_path: Path, out_dir: Path | None = None) -> dict[str, Path]:
    """Audit a conversation.json file and write JSON + markdown reports."""
    data = json.loads(conversation_path.read_text(encoding="utf-8"))
    audit = audit_conversation(data)
    audit["source_file"] = str(conversation_path)

    out = out_dir or conversation_path.parent
    out.mkdir(parents=True, exist_ok=True)
    stem = conversation_path.stem

    json_path = out / f"{stem}_grounding_audit.json"
    json_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path = out / f"{stem}_grounding_audit.md"
    md_path.write_text(
        _build_markdown(audit, str(conversation_path)), encoding="utf-8"
    )
    return {"json": json_path, "markdown": md_path}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grounding audit — replay a saved F1 conversation.json "
                    "through the runtime grounding filter"
    )
    parser.add_argument("conversation_json", help="Path to a *_conversation.json file")
    parser.add_argument(
        "--out", default=None, help="Output directory (default: alongside the input)"
    )
    args = parser.parse_args()

    path = Path(args.conversation_json)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    out_dir = Path(args.out) if args.out else None
    paths = audit_file(path, out_dir)

    audit = json.loads(paths["json"].read_text(encoding="utf-8"))
    counts = audit["counts"]
    print(f"Grounding audit — {audit.get('persona_id') or audit.get('session_id')}")
    print(f"  grounded={counts.get('grounded', 0)} "
          f"negative_grounded={counts.get('negative_grounded', 0)} "
          f"ungrounded={counts.get('ungrounded', 0)} "
          f"system_slot={counts.get('system_slot', 0)}")
    print(f"  recomputed grounded coverage: {audit['recomputed_grounded_coverage']}")
    for s in audit["slots"]:
        if s["verdict"] == "ungrounded":
            print(f"  [UNGROUNDED] {s['key']}: {s['value'][:60]!r} — {s['reason']}")
    print(f"  Written: {paths['json']}, {paths['markdown']}")


if __name__ == "__main__":
    main()
